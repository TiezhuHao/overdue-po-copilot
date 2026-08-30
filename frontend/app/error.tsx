"use client";
import Link from "next/link";
export default function Error({ reset }: { reset: () => void }) { return <main><div className="error-box" role="alert"><h2>页面暂时无法显示</h2><p>请重试，或返回工作台重新选择订单。</p><button className="primary" onClick={reset}>重试</button><Link className="back-link" href="/">返回工作台</Link></div></main>; }
