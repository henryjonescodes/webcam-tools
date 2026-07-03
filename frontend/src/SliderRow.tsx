import * as Slider from "@radix-ui/react-slider";

interface Props {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
  displayValue?: string;
  onChange: (value: number) => void;
}

export default function SliderRow({ label, value, min, max, step = 1, disabled, displayValue, onChange }: Props) {
  return (
    <div className="slider-row">
      <span className="slider-label">{label}</span>
      <Slider.Root
        className="slider-root"
        min={min}
        max={max}
        step={step}
        value={[value]}
        disabled={disabled}
        onValueChange={([v]) => onChange(v)}
      >
        <Slider.Track className="slider-track">
          <Slider.Range className="slider-range" />
        </Slider.Track>
        <Slider.Thumb className="slider-thumb" />
      </Slider.Root>
      <span className="slider-value">{displayValue ?? value}</span>
    </div>
  );
}
