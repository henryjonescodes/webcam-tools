import * as Switch from "@radix-ui/react-switch";

interface Props {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
}

export default function ToggleSwitch({ checked, onChange, disabled }: Props) {
  return (
    <Switch.Root className="ios-switch" checked={checked} onCheckedChange={onChange} disabled={disabled}>
      <Switch.Thumb className="ios-switch-thumb" />
    </Switch.Root>
  );
}
