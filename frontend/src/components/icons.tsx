import type { ReactNode } from "react";

type IconProps = {
  className?: string;
};

export function SearchIcon({ className }: IconProps = {}) {
  return <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" />
  </svg>;
}

export function FilterIcon({ className }: IconProps = {}) {
  return <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 6h16M7 12h10M10 18h4" />
  </svg>;
}

export function CalendarIcon({ className }: IconProps = {}) {
  return <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" />
  </svg>;
}

export function PaperclipIcon() {
  return (
    <svg aria-hidden="true" className="composer-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="M 17.916667 26.666667 29.166667 15.416667 a 6.666667 6.666667 0 0 1 9.375 9.375 l -14.375 14.375 a 10.416667 10.416667 0 0 1 -14.791667 -14.791667 l 15 -15"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="m 20.416667 29.166667 13.125 -13.125"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function ArrowUpIcon() {
  return (
    <svg aria-hidden="true" className="composer-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="M 25 39.583333 V 10.416667 m 0 0 -12.5 12.5 m 12.5 -12.5 12.5 12.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function ArrowDownIcon({ className = "conversation-tail-button-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="M 25 10.416667 v 29.166667 m 0 0 12.5 -12.5 m -12.5 12.5 -12.5 -12.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function DownloadIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="M 25 8.333333 v 22.916667 m 0 0 8.333333 -8.333333 m -8.333333 8.333333 -8.333333 -8.333333 M 10.416667 39.583333 h 29.166667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function UploadIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 25 31.25 V 8.333333 m 0 0 L 16.666667 16.666667 m 8.333333 -8.333333 8.333333 8.333333 M 10.416667 29.166667 v 9.375 A 3.125 3.125 0 0 0 13.541667 41.666667 h 22.916667 a 3.125 3.125 0 0 0 3.125 -3.125 V 29.166667" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function StopIcon() {
  return <span aria-hidden="true" className="stop-icon" />;
}

export function TurnRightIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 8.333333 10.416667 v 12.5 a 8.333333 8.333333 0 0 0 8.333333 8.333333 h 25 M 31.25 20.833333 41.666667 31.25 31.25 41.666667" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function SwapHorizontalIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 37.5 18.75 H 12.5 l 8.333333 -8.333333 M 12.5 31.25 h 25 l -8.333333 8.333333" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function GripIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <g fill="currentColor">
        <circle cx="16.666667" cy="12.5" r="3.125" />
        <circle cx="33.333333" cy="12.5" r="3.125" />
        <circle cx="16.666667" cy="25" r="3.125" />
        <circle cx="33.333333" cy="25" r="3.125" />
        <circle cx="16.666667" cy="37.5" r="3.125" />
        <circle cx="33.333333" cy="37.5" r="3.125" />
      </g>
    </SettingsLineIcon>
  );
}

export function WaitingIcon() {
  return (
    <svg aria-hidden="true" fill="none" viewBox="0 0 50 50">
      <path
        d="M 41.666667 25 a 16.666667 16.666667 0 1 1 -4.895833 -11.770833"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function TrashIcon({ className = "sidebar-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="M 8.333333 14.583333 h 33.333333 m -20.833333 8.333333 v 12.5 m 8.333333 -12.5 v 12.5 M 13.541667 14.583333 l 1.666667 27.083333 h 19.583333 l 1.666667 -27.083333 M 18.75 14.583333 l 1.041667 -6.25 h 10.416667 L 31.25 14.583333"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function SidebarExpandedIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-action-icon sidebar-layout-icon" fill="none" viewBox="0 0 50 50">
      <rect
        height="31.25"
        rx="6.25"
        stroke="currentColor"
        strokeWidth="5"
        width="35.416667"
        x="7.291667"
        y="9.375"
      />
      <path
        d="M 18.75 10.416667 v 29.166667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function SidebarCollapsedIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-action-icon sidebar-layout-icon" fill="none" viewBox="0 0 50 50">
      <rect
        height="31.25"
        rx="6.25"
        stroke="currentColor"
        strokeWidth="5"
        width="35.416667"
        x="7.291667"
        y="9.375"
      />
      <path
        d="M 14.166667 16.666667 v 16.666667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function PlusIcon({ className = "nav-icon" }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 25 10.416667 v 29.166667 M 10.416667 25 h 29.166667" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function ReportScenarioIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="M 10.416667 39.583333 h 29.166667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="5"
      />
      <rect
        height="14.583333"
        rx="2.5"
        stroke="currentColor"
        strokeWidth="5"
        width="7.916667"
        x="12.5"
        y="20.833333"
      />
      <rect
        height="22.916667"
        rx="2.5"
        stroke="currentColor"
        strokeWidth="5"
        width="7.916667"
        x="21.041667"
        y="12.5"
      />
      <rect
        height="10.416667"
        rx="2.5"
        stroke="currentColor"
        strokeWidth="5"
        width="7.916667"
        x="29.583333"
        y="25"
      />
    </svg>
  );
}

export function HealthRecordIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="M 13.541667 7.291667 h 15 L 37.5 16.25 v 26.458333 H 13.541667 v -35.416667 Z"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="M 28.125 7.916667 V 16.666667 h 8.75 M 18.75 25 h 12.5 M 18.75 32.291667 h 12.5 M 18.75 39.583333 h 6.666667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function FavoriteNavIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="m 25 7.916667 5.208333 10.416667 11.458333 1.666667 -8.333333 8.125 1.875 11.458333 -10.208333 -5.416667 L 14.791667 39.583333 l 1.875 -11.458333 -8.333333 -8.125 11.458333 -1.666667 L 25 7.916667 Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function CopyIcon() {
  return (
    <svg aria-hidden="true" className="message-action-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="M 16.666667 17.708333 V 14.583333 a 6.25 6.25 0 0 1 6.25 -6.25 h 12.5 a 6.25 6.25 0 0 1 6.25 6.25 v 12.5 a 6.25 6.25 0 0 1 -6.25 6.25 h -3.125"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <rect
        height="25"
        rx="6.25"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
        width="25"
        x="8.333333"
        y="16.666667"
      />
    </svg>
  );
}

export function EditIcon({ className = "message-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="m 8.333333 41.666667 10 -2.083333 20.625 -20.625 a 4.791667 4.791667 0 0 0 -6.875 -6.875 l -20.625 20.625 L 8.333333 41.666667 Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="m 29.166667 14.583333 6.25 6.25"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function QuoteIcon() {
  return (
    <svg aria-hidden="true" className="selection-annotation-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="M 16.666667 38.541667 h 15 c 5.625 0 10 -4.166667 10 -9.583333 V 20 C 41.666667 14.583333 37.291667 10.416667 31.666667 10.416667 H 18.333333 C 12.708333 10.416667 8.333333 14.583333 8.333333 20 v 8.958333 c 0 3.125 1.458333 5.833333 3.958333 7.5 L 11.458333 43.75 16.666667 38.541667 Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function RegenerateIcon() {
  return (
    <svg aria-hidden="true" className="message-action-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="M 39.583333 18.75 a 14.583333 14.583333 0 1 0 2.083333 8.333333"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="M 39.583333 8.333333 v 10.416667 h -10.416667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function BranchIcon({ className = "message-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="M 10.416667 25 h 6.666667 c 4.375 0 6.666667 -2.083333 9.791667 -5.208333 L 39.583333 7.291667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="M 30.208333 7.291667 H 39.583333 V 16.666667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="M 17.083333 25 c 4.375 0 6.666667 2.083333 9.791667 5.208333 L 39.583333 42.708333"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="M 30.208333 42.708333 H 39.583333 V 33.333333"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function StarIcon({
  filled = false,
  className = "message-action-icon"
}: {
  filled?: boolean;
  className?: string;
} = {}) {
  return (
    <svg aria-hidden="true" className={className} fill={filled ? "currentColor" : "none"} viewBox="0 0 50 50">
      <path
        d="m 25 7.916667 5.208333 10.416667 11.458333 1.666667 -8.333333 8.125 1.875 11.458333 -10.208333 -5.416667 L 14.791667 39.583333 l 1.875 -11.458333 -8.333333 -8.125 11.458333 -1.666667 L 25 7.916667 Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function EyeIcon({ className = "secret-toggle-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="M 7.916667 25 s 6.25 -10.833333 17.083333 -10.833333 17.083333 10.833333 17.083333 10.833333 -6.25 10.833333 -17.083333 10.833333 S 7.916667 25 7.916667 25 Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <circle cx="25" cy="25" r="5" stroke="currentColor" strokeWidth="5" />
    </svg>
  );
}

export function EyeOffIcon({ className = "secret-toggle-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="m 9.375 9.375 31.25 31.25"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="M 18.333333 12.916667 a 17.708333 17.708333 0 0 1 6.666667 -1.25 c 10.833333 0 17.083333 10.833333 17.083333 10.833333 a 31.25 31.25 0 0 1 -4.583333 5.833333 M 29.583333 33.333333 a 17.916667 17.916667 0 0 1 -4.583333 0.625 c -10.833333 0 -17.083333 -10.833333 -17.083333 -10.833333 a 30.208333 30.208333 0 0 1 6.25 -7.083333"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
      <path
        d="M 21.458333 21.458333 a 5 5 0 0 0 7.083333 7.083333"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

function SettingsLineIcon({ children, className = "settings-nav-icon" }: IconProps & {
  children: ReactNode;
}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      {children}
    </svg>
  );
}

const settingsLineIconProps = {
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  strokeWidth: 5
};

export function UserIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <circle cx="25" cy="16.666667" r="7.291667" {...settingsLineIconProps} />
      <path d="M 11.458333 41.666667 c 1.25 -8.333333 5.833333 -12.5 13.541667 -12.5 s 12.291667 4.166667 13.541667 12.5" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function BrainIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 25 8.333333 c -3.125 -4.166666 -9.375 -3.125 -11.458333 1.041667 c -5.208334 -1.041667 -8.333334 4.166667 -6.25 9.375 c -4.166667 4.166667 -2.083334 10.416667 2.083333 11.458333 c -2.083333 5.208334 2.083333 10.416667 7.291667 9.375 c 2.083333 4.166667 7.291666 3.125 8.333333 -1.041666 c 1.041667 4.166666 6.25 5.208333 8.333333 1.041666 c 5.208334 1.041667 9.375 -4.166666 7.291667 -9.375 c 4.166667 -1.041666 6.25 -7.291666 2.083333 -11.458333 c 2.083334 -5.208333 -1.041666 -10.416667 -6.25 -9.375 c -2.083333 -4.166667 -8.333333 -5.208333 -11.458333 -1.041667 Z" {...settingsLineIconProps} />
      <path d="M 25 8.333333 v 30.208334" {...settingsLineIconProps} />
      <path d="M 13.541667 16.666667 c 4.166666 -1.041667 7.291666 2.083333 6.25 5.208333 M 9.375 27.083333 c 4.166667 -2.083333 7.291667 0 7.291667 3.125 M 14.583333 35.416667 c 3.125 -3.125 6.25 -2.083334 7.291667 0 M 36.458333 16.666667 c -4.166666 -1.041667 -7.291666 2.083333 -6.25 5.208333 M 40.625 27.083333 c -4.166667 -2.083333 -7.291667 0 -7.291667 3.125 M 35.416667 35.416667 c -3.125 -3.125 -6.25 -2.083334 -7.291667 0" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function LockIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <rect height="20.833333" rx="4.166667" width="29.166667" x="10.416667" y="20.833333" {...settingsLineIconProps} />
      <path d="M 16.666667 20.833333 V 15.625 a 8.333333 8.333333 0 0 1 16.666667 0 V 20.833333 M 25 29.166667 v 4.166667" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function ServerIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <rect height="12.5" rx="4.166667" width="33.333333" x="8.333333" y="8.333333" {...settingsLineIconProps} />
      <rect height="12.5" rx="4.166667" width="33.333333" x="8.333333" y="29.166667" {...settingsLineIconProps} />
      <path d="M 16.666667 14.583333 h 0.020833 M 16.666667 35.416667 h 0.020833 M 25 14.583333 h 10.416667 M 25 35.416667 h 10.416667" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function SlidersIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 8.333333 14.583333 h 12.5 M 29.166667 14.583333 h 12.5 M 8.333333 35.416667 h 20.833333 M 37.5 35.416667 h 4.166667" {...settingsLineIconProps} />
      <circle cx="25" cy="14.583333" r="4.166667" {...settingsLineIconProps} />
      <circle cx="33.333333" cy="35.416667" r="4.166667" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function ImageFormatIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <rect height="33.333333" rx="4.166667" width="37.5" x="6.25" y="8.333333" {...settingsLineIconProps} />
      <circle cx="17.708333" cy="18.75" r="3.125" {...settingsLineIconProps} />
      <path d="m 11.458333 35.416667 8.75 -8.75 6.458333 6.458333 4.791667 -4.791667 7.083333 7.083333" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function TextFormatIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 12.5 10.416667 h 25 M 25 10.416667 v 29.166667 M 17.708333 39.583333 h 14.583333" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function AudioFormatIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 8.333333 27.083333 v -4.166667 a 16.666667 16.666667 0 0 1 33.333333 0 v 4.166667" {...settingsLineIconProps} />
      <rect height="14.583333" rx="4.166667" width="8.333333" x="6.25" y="25" {...settingsLineIconProps} />
      <rect height="14.583333" rx="4.166667" width="8.333333" x="35.416667" y="25" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function VideoFormatIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <rect height="25" rx="4.166667" width="27.083333" x="6.25" y="12.5" {...settingsLineIconProps} />
      <path d="m 33.333333 20.833333 10.416667 -4.166667 v 16.666667 l -10.416667 -4.166667 Z" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function DocumentFormatIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 12.5 6.25 h 16.666667 l 8.333333 8.333333 v 29.166667 H 12.5 Z" {...settingsLineIconProps} />
      <path d="M 29.166667 6.25 v 10.416667 h 10.416667 M 18.75 27.083333 h 12.5 M 18.75 35.416667 h 12.5" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function OtherFormatIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <circle cx="10.416667" cy="25" r="2.083333" fill="currentColor" />
      <circle cx="25" cy="25" r="2.083333" fill="currentColor" />
      <circle cx="39.583333" cy="25" r="2.083333" fill="currentColor" />
    </SettingsLineIcon>
  );
}

export function ToolCallingIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 30.208333 11.458333 a 8.333333 8.333333 0 0 0 -10.416667 10.416667 L 8.333333 33.333333 l 8.333333 8.333333 11.458333 -11.458333 a 8.333333 8.333333 0 0 0 10.416667 -10.416667 l -6.25 6.25 -6.25 -6.25 6.25 -6.25 Z" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export type ExecutionStage = "context" | "reasoning" | "tool" | "content" | "observation";

export function ExecutionStageIcon({ stage }: { stage: ExecutionStage }) {
  const paths: Record<ExecutionStage, ReactNode> = {
    context: <path d="M 14.583333 6.25 h 16.666667 l 8.333333 8.333333 v 29.166667 H 14.583333 z M 31.25 6.25 v 10.416667 h 10.416667 M 20.833333 25 h 12.5 M 20.833333 33.333333 h 12.5" {...settingsLineIconProps} />,
    reasoning: <path d="M 18.75 37.5 h 12.5 M 20.833333 43.75 h 8.333333 M 17.083333 30.625 a 14.583333 14.583333 0 1 1 15.833333 0 c -2.291667 1.666667 -3.125 3.333333 -3.125 4.791667 h -9.583333 c 0 -1.458333 -0.833333 -3.125 -3.125 -4.791667 Z" {...settingsLineIconProps} />,
    tool: <path d="M 10.416667 14.583333 h 29.166667 M 10.416667 35.416667 h 29.166667 M 16.666667 8.333333 v 12.5 m 16.666667 8.333333 v 12.5" {...settingsLineIconProps} />,
    content: <path d="M 12.5 8.333333 h 25 v 33.333333 H 12.5 z M 18.75 16.666667 h 12.5 M 18.75 25 h 12.5 M 18.75 33.333333 h 8.333333" {...settingsLineIconProps} />,
    observation: <path d="M 8.333333 25 h 27.083333 m -10.416667 -10.416667 10.416667 10.416667 -10.416667 10.416667 M 41.666667 10.416667 v 29.166667" {...settingsLineIconProps} />
  };
  return (
    <SettingsLineIcon className="execution-record-icon">
      {paths[stage]}
    </SettingsLineIcon>
  );
}

export function MessageIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 10.416667 38.541667 9.375 43.75 l 6.25 -3.541667 h 18.75 A 7.291667 7.291667 0 0 0 41.666667 32.916667 V 15.625 A 7.291667 7.291667 0 0 0 34.375 8.333333 h -18.75 A 7.291667 7.291667 0 0 0 8.333333 15.625 V 31.25 c 0 2.916667 0.833333 5.208333 2.083333 7.291667 Z" {...settingsLineIconProps} />
      <path d="M 16.666667 18.75 h 16.666667 M 16.666667 27.083333 h 10.416667" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function GlobeIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <circle cx="25" cy="25" r="18.75" {...settingsLineIconProps} />
      <path d="M 7.291667 25 h 35.416667 M 25 6.25 c 4.583333 5 6.666667 11.25 6.666667 18.75 s -2.083333 13.75 -6.666667 18.75 c -4.583333 -5 -6.666667 -11.25 -6.666667 -18.75 S 20.416667 11.25 25 6.25 Z" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function ListTreeIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 12.5 10.416667 v 29.166667 M 12.5 16.666667 h 8.333333 M 12.5 33.333333 h 8.333333" {...settingsLineIconProps} />
      <rect height="10.416667" rx="3.125" width="16.666667" x="20.833333" y="11.458333" {...settingsLineIconProps} />
      <rect height="10.416667" rx="3.125" width="16.666667" x="20.833333" y="28.125" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function ListChecksIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="m 8.333333 14.583333 3.125 3.125 L 16.666667 12.5 M 22.916667 14.583333 h 18.75 M 8.333333 27.083333 l 3.125 3.125 L 16.666667 25 M 22.916667 27.083333 h 18.75 M 8.333333 39.583333 l 3.125 3.125 L 16.666667 37.5 M 22.916667 39.583333 h 18.75" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function TagIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 8.333333 10.416667 h 16.666667 l 16.666667 16.666666 -16.666667 16.666667 -16.666667 -16.666667 Z" {...settingsLineIconProps} />
      <path d="M 18.75 20.833333 h 0.020833" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function MergeIcon({ className }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 10.416667 41.666667 v -6.25 c 0 -10.416667 14.583333 -8.333333 14.583333 -18.75 V 8.333333 M 39.583333 41.666667 v -6.25 c 0 -10.416667 -14.583333 -8.333333 -14.583333 -18.75 M 16.666667 16.666667 25 8.333333 l 8.333333 8.333334" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function ChevronDownIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="m 10.416667 17.708333 14.583333 14.583333 14.583333 -14.583333" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function InfoIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <circle cx="25" cy="25" r="18.75" {...settingsLineIconProps} />
      <path d="M 25 22.916667 v 10.416667 M 25 16.666667 h 0.020833" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function AlertIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 21.25 9.583333 7.916667 35.416667 a 4.166667 4.166667 0 0 0 3.75 6.041667 h 26.666667 a 4.166667 4.166667 0 0 0 3.75 -6.041667 L 28.75 9.583333 a 4.166667 4.166667 0 0 0 -7.5 0 Z" {...settingsLineIconProps} />
      <path d="M 25 18.75 v 8.333333 M 25 33.333333 h 0.020833" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function LightningIcon() {
  return (
    <svg aria-hidden="true" className="settings-action-icon lightning-action-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="M 27.083333 4.166667 10.416667 27.083333 h 12.5 l -2.083333 18.75 18.75 -27.083333 h -12.5 l 2.083333 -14.583333 Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function CheckIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="m 10.416667 25 8.75 8.75 L 39.583333 14.166667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function ChevronLeftIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="m 31.25 10.416667 -14.583333 14.583333 14.583333 14.583333"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function ChevronRightIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="m 18.75 10.416667 14.583333 14.583333 -14.583333 14.583333"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function PinIcon({ className = "conversation-pin-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 50 50">
      <path
        d="M 12.5 6.25 h 25 M 16.666667 6.25 v 14.583333 a 10.416667 10.416667 0 0 1 -4.166667 6.25 v 8.333333 h 25 v -8.333333 a 10.416667 10.416667 0 0 1 -4.166667 -6.25 V 6.25 M 10.416667 35.416667 h 29.166667 M 25 35.416667 v 10.416667"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function LogOutIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <SettingsLineIcon className={className}>
      <path d="M 18.75 43.75 H 10.416667 A 4.166667 4.166667 0 0 1 6.25 39.583333 V 10.416667 A 4.166667 4.166667 0 0 1 10.416667 6.25 H 18.75" {...settingsLineIconProps} />
      <path d="M 18.75 25 H 43.75 M 33.333333 14.583333 43.75 25 33.333333 35.416667" {...settingsLineIconProps} />
    </SettingsLineIcon>
  );
}

export function XIcon() {
  return (
    <svg aria-hidden="true" className="settings-action-icon" fill="none" viewBox="0 0 50 50">
      <path
        d="m 12.5 12.5 25 25 M 37.5 12.5 12.5 37.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="5"
      />
    </svg>
  );
}

export function MedicineBoxIcon({ className }: IconProps = {}) {
  return <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="7" width="18" height="14" rx="2" />
    <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M12 11v6M9 14h6" />
  </svg>;
}

export function MedicationIcon({ className }: IconProps = {}) {
  return <svg aria-hidden="true" className={className} viewBox="0 0 50 50" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M12 38a10 10 0 0 1 0-14l12-12a10 10 0 0 1 14 14L26 38a10 10 0 0 1-14 0Z" stroke="currentColor" strokeWidth="5" strokeLinejoin="round" />
    <path d="m18 18 14 14" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
  </svg>;
}
