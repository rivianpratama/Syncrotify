import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
  icon?: ReactNode;
}

export function Button({
  variant = "secondary",
  icon,
  children,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button className={`button ${variant} ${className}`} type="button" {...props}>
      {icon}
      <span>{children}</span>
    </button>
  );
}

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}

export function Switch({ checked, onChange, label }: SwitchProps) {
  return (
    <label className="switch-row">
      <button
        aria-checked={checked}
        aria-label={label}
        className={`switch ${checked ? "on" : ""}`}
        onClick={() => onChange(!checked)}
        role="switch"
        type="button"
      >
        <span />
      </button>
      <span>{label}</span>
    </label>
  );
}

interface ProgressBarProps {
  value: number;
  tone?: "accent" | "success";
}

export function ProgressBar({ value, tone = "accent" }: ProgressBarProps) {
  return (
    <div
      aria-label={`${Math.round(value)} percent`}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={value}
      className={`progress-track ${tone}`}
      role="progressbar"
    >
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}
