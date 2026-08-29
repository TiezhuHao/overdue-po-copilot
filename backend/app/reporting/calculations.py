"""Report-adjacent calculation that is not a source Report 4 column."""
from decimal import Decimal


def estimated_consumption(overdue_open_qty, weekly_average_demand_qty):
    if overdue_open_qty < 0 or weekly_average_demand_qty < 0:
        raise ValueError('NEGATIVE_CONSUMPTION_INPUT')
    if weekly_average_demand_qty == 0:
        return {'estimated_consumption_months': None, 'consumption_status': 'NO_FORECAST_DEMAND'}
    return {'estimated_consumption_months': overdue_open_qty / weekly_average_demand_qty * Decimal(12) / Decimal(52),
            'consumption_status': 'FORECAST_AVAILABLE'}
