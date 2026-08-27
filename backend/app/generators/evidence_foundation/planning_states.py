"""Construct persistent quantity states jointly across overlapping planning events.

This generator-only constraint model does not alter evaluation thresholds. Dates
and quantities are its output; labels never enter the persisted source facts.
"""

from bisect import bisect_right
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import numpy as np
from scipy.optimize import linprog

from app.generators.evidence_foundation.calendar import add_months


def plan_monthly_states(anchors, change, scenario_config):
    anchors = sorted(set(anchors))
    first = anchors[0].replace(day=1)
    end = add_months(anchors[-1].replace(day=1), scenario_config.comparison_months)
    months = []
    while first < end:
        months.append(first)
        first = add_months(first, 1)
    width = len(months)
    states = len(anchors) + 1
    n = width * states
    # Auxiliary L1 distances keep initial quantities near a flat planning budget.
    total_variables = n + width
    inequalities, limits, equalities, targets = [], [], [], []

    def vector(state, selected):
        row = np.zeros(total_variables)
        for m in selected:
            row[state * width + m] = 1
        return row

    def upper(row, limit=0):
        inequalities.append(row)
        limits.append(limit)

    margin = Decimal('0.01')
    for i, anchor in enumerate(anchors, 1):
        start = anchor.replace(day=1)
        near_end = add_months(start, scenario_config.delay_near_term_months)
        window_end = add_months(start, scenario_config.comparison_months)
        near = [m for m, day in enumerate(months) if start <= day < near_end]
        far = [m for m, day in enumerate(months) if near_end <= day < window_end]
        # Source state changes only at the event; earlier history is immutable.
        for m, day in enumerate(months):
            if day < start or day >= window_end:
                equalities.append(vector(i, [m]) - vector(i - 1, [m]))
                targets.append(0)
        before_states = {bisect_right(anchors, anchor - timedelta(days=d)) for d in range(1, 15)}
        after_states = {bisect_right(anchors, anchor + timedelta(days=d)) for d in range(1, 43)}
        for b in sorted(before_states):
            nb, fb = vector(b, near), vector(b, far)
            tb = nb + fb
            upper(-tb, -7)
            upper(-nb, -1)
            for p in sorted(after_states):
                np_, fp = vector(p, near), vector(p, far)
                tp = np_ + fp
                if change == 'REDUCTION':
                    upper(tp - float(1 - scenario_config.reduction_total_drop_ratio - margin) * tb)
                    upper(fp - fb)
                elif change == 'DELAY':
                    equalities.append(tp - tb)
                    targets.append(0)
                    upper(np_ - float(1 - scenario_config.delay_near_term_drop_ratio - margin) * nb)
                    upper(fb + float(scenario_config.delay_shift_share_min + margin) * nb - fp)
                elif change == 'MIXED':
                    upper(tp - float(1 - scenario_config.mixed_total_drop_ratio - margin) * tb)
                    upper(fb + float(scenario_config.mixed_shift_share_min + margin) * nb - fp)
                else:
                    raise ValueError('unsupported source quantity shape')
    for m in range(width):
        row = vector(0, [m])
        row[n + m] = -1
        upper(row, 1)
        row = -vector(0, [m])
        row[n + m] = -1
        upper(row, -1)
    objective = np.zeros(total_variables)
    objective[:n] = np.linspace(1e-5, 2e-5, n)
    objective[n:] = 1
    solved = linprog(objective, A_ub=inequalities, b_ub=limits,
                     A_eq=equalities or None, b_eq=targets or None,
                     bounds=(0, None), method='highs-ds',
                     options={'primal_feasibility_tolerance': 1e-9,
                              'dual_feasibility_tolerance': 1e-9})
    if not solved.success:
        raise ValueError('INCOMPATIBLE_PERSISTENT_PLANNING_STATES')
    return months, [[Decimal(str(max(0, solved.x[s * width + m])))
                     for m in range(width)] for s in range(states)]


def persistent_daily_states(anchors, change, scenario_config, original, reference):
    if change == 'NONE' or not anchors:
        return [dict(original) for _ in range(len(anchors) + 1)]
    months, quantities = plan_monthly_states(anchors, change, scenario_config)
    quantum = Decimal('0.0001')
    result = []
    for state in quantities:
        # The finite programme is planned in the original anchor comparison
        # horizons, not invented independently by later report generators.
        daily = {day: qty if day < months[0] else Decimal(0)
                 for day, qty in original.items()}
        for month, normalized in zip(months, state):
            bucket = sorted(day for day in original if day.replace(day=1) == month)
            if not bucket or bucket[-1] + timedelta(days=1) != add_months(month, 1):
                raise ValueError('INCOMPLETE_DEMAND_HORIZON')
            total = (normalized * reference * 30).quantize(quantum, rounding=ROUND_HALF_UP)
            weight = sum(original[day] for day in bucket)
            if weight <= 0:
                raise ValueError('INCOMPATIBLE_PLANNING_REFERENCE')
            # Largest remainder allocation preserves exact Decimal month totals.
            amounts = [(total * original[day] / weight / quantum) for day in bucket]
            units = [int(amount) for amount in amounts]
            remaining = int(total / quantum) - sum(units)
            order = sorted(range(len(bucket)), key=lambda i: (-(amounts[i] - units[i]), bucket[i]))
            for i in order[:remaining]:
                units[i] += 1
            daily.update({day: quantum * unit for day, unit in zip(bucket, units)})
        result.append(daily)
    return result
