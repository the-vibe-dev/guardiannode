interface Props {
  severity: string;
}

const colors: Record<string, string> = {
  critical: "bg-severity-critical text-white",
  high: "bg-severity-high text-white",
  medium: "bg-severity-medium text-black",
  low: "bg-severity-low text-white",
  none: "bg-severity-none text-white",
};

export default function SeverityBadge({ severity }: Props) {
  const cls = colors[severity] || colors.none;
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase ${cls}`}>
      {severity}
    </span>
  );
}
