interface ToggleProps {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  title?: string;
  label?: string;
  size?: "sm" | "md";
}

export function Toggle({ checked, onChange, disabled, title, label, size = "md" }: ToggleProps) {
  const dims = size === "sm" ? "h-4 w-7" : "h-5 w-9";
  const knob = size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5";
  const shift = size === "sm" ? "translate-x-3.5" : "translate-x-4";
  return (
    <label className={`inline-flex items-center gap-2 ${disabled ? "opacity-50" : "cursor-pointer"}`} title={title}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={(e) => {
          e.stopPropagation();
          onChange(!checked);
        }}
        className={`relative inline-flex ${dims} items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 ${
          checked ? "bg-green-500" : "bg-gray-300"
        }`}
      >
        <span
          className={`inline-block ${knob} transform rounded-full bg-white shadow transition-transform ${
            checked ? shift : "translate-x-0.5"
          }`}
        />
      </button>
      {label && <span className="text-sm text-gray-700">{label}</span>}
    </label>
  );
}
