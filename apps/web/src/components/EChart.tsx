"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";

export const CHART_COLORS = ["#ffb000", "#2dd4bf", "#ff3b30", "#8aa3c0", "#4ade80", "#e879f9"];

export const baseTextStyle = {
  color: "#6b7a8f",
  fontFamily: "IBM Plex Mono, monospace",
  fontSize: 10,
};

export default function EChart({
  option,
  height = 280,
  onClick,
}: {
  option: echarts.EChartsOption;
  height?: number;
  onClick?: (params: echarts.ECElementEvent) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  // keep the latest handler in a ref so inline onClick props don't force a
  // full setOption redraw on every parent re-render
  const onClickRef = useRef(onClick);
  onClickRef.current = onClick;

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.on("click", (p) => onClickRef.current?.(p as echarts.ECElementEvent));
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.setOption(
      {
        color: CHART_COLORS,
        backgroundColor: "transparent",
        textStyle: baseTextStyle,
        tooltip: { trigger: "axis", backgroundColor: "#141c28", borderColor: "#1d2836", textStyle: { color: "#c9d4e3", fontSize: 11 } },
        grid: { left: 48, right: 16, top: 24, bottom: 28 },
        ...option,
      },
      true
    );
  }, [option]);

  return <div ref={ref} style={{ height }} className="w-full" />;
}
