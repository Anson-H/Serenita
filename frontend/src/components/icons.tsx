type IconProps = {
  className?: string;
};

export function PaperclipIcon() {
  return (
    <svg aria-hidden="true" className="composer-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M8.6 12.8 14 7.4a3.2 3.2 0 0 1 4.5 4.5l-6.9 6.9a5 5 0 0 1-7.1-7.1l7.2-7.2"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="m9.8 14 6.3-6.3"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function ArrowUpIcon() {
  return (
    <svg aria-hidden="true" className="composer-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M12 19V5m0 0-6 6m6-6 6 6"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.3"
      />
    </svg>
  );
}

export function StopIcon() {
  return <span aria-hidden="true" className="stop-icon" />;
}

export function TrashIcon({ className = "sidebar-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24">
      <path
        d="M4 7h16m-10 4v6m4-6v6M6.5 7l.8 13h9.4l.8-13M9 7l.5-3h5L15 7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function SidebarBackIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-action-icon sidebar-back-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="m15 5.5-6.5 6.5 6.5 6.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.4"
      />
    </svg>
  );
}

export function SidebarCloseIcon() {
  return (
    <svg aria-hidden="true" className="sidebar-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="m6.5 6.5 11 11M17.5 6.5l-11 11"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.4"
      />
    </svg>
  );
}

export function PlusIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M12 5v14M5 12h14"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.4"
      />
    </svg>
  );
}

export function ReportScenarioIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M5 19h14"
        stroke="currentColor"
        strokeLinecap="round"
        strokeWidth="2"
      />
      <rect
        height="7"
        rx="1.2"
        stroke="currentColor"
        strokeWidth="2"
        width="3.8"
        x="6"
        y="10"
      />
      <rect
        height="11"
        rx="1.2"
        stroke="currentColor"
        strokeWidth="2"
        width="3.8"
        x="10.1"
        y="6"
      />
      <rect
        height="5"
        rx="1.2"
        stroke="currentColor"
        strokeWidth="2"
        width="3.8"
        x="14.2"
        y="12"
      />
    </svg>
  );
}

export function LifestyleScenarioIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M12 20c4.2-1.9 6.5-5.1 6.5-9.4V5.5h-5.1C9.1 5.5 6 8.6 6 12.9V18h4.7"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M18.2 5.8 9.4 14.6m1.1-5.1h4.6v4.6"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function HealthRecordIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M6.5 3.5h7.2L18 7.8v12.7H6.5v-17Z"
        stroke="currentColor"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M13.5 3.8V8h4.2M9 12h6M9 15.5h6M9 19h3.2"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function FavoriteNavIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="m12 3.8 2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6L7.1 19l.9-5.5-4-3.9 5.5-.8L12 3.8Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function SettingsNavIcon() {
  return (
    <svg aria-hidden="true" className="nav-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M12 8.2a3.8 3.8 0 1 1 0 7.6 3.8 3.8 0 0 1 0-7.6Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M18.7 13.2c.1-.4.1-.8.1-1.2s0-.8-.1-1.2l2-1.5-2-3.5-2.4 1a8 8 0 0 0-2.1-1.2L14 3h-4l-.4 2.6c-.8.3-1.5.7-2.1 1.2l-2.4-1-2 3.5 2 1.5c-.1.4-.1.8-.1 1.2s0 .8.1 1.2l-2 1.5 2 3.5 2.4-1c.6.5 1.3.9 2.1 1.2L10 21h4l.4-2.6c.8-.3 1.5-.7 2.1-1.2l2.4 1 2-3.5-2.2-1.5Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function CopyIcon() {
  return (
    <svg aria-hidden="true" className="message-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M8 8.5V7a3 3 0 0 1 3-3h6a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-1.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <rect
        height="12"
        rx="3"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
        width="12"
        x="4"
        y="8"
      />
    </svg>
  );
}

export function EditIcon() {
  return (
    <svg aria-hidden="true" className="message-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="m4 20 4.8-1 9.9-9.9a2.3 2.3 0 0 0-3.3-3.3l-9.9 9.9L4 20Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="m14 7 3 3"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function QuoteIcon() {
  return (
    <svg aria-hidden="true" className="selection-quote-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M8 18.5h7.2c2.7 0 4.8-2 4.8-4.6V9.6C20 7 17.9 5 15.2 5H8.8C6.1 5 4 7 4 9.6v4.3c0 1.5.7 2.8 1.9 3.6L5.5 21 8 18.5Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function RegenerateIcon() {
  return (
    <svg aria-hidden="true" className="message-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M19 9a7 7 0 1 0 1 4"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M19 4v5h-5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function BranchIcon() {
  return (
    <svg aria-hidden="true" className="message-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M5 12h3.2c2.1 0 3.2-1 4.7-2.5L19 3.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M14.5 3.5H19V8"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M8.2 12c2.1 0 3.2 1 4.7 2.5L19 20.5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M14.5 20.5H19V16"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
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
    <svg aria-hidden="true" className={className} fill={filled ? "currentColor" : "none"} viewBox="0 0 24 24">
      <path
        d="m12 3.8 2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6L7.1 19l.9-5.5-4-3.9 5.5-.8L12 3.8Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function EyeIcon({ className = "secret-toggle-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24">
      <path
        d="M3.8 12s3-5.2 8.2-5.2 8.2 5.2 8.2 5.2-3 5.2-8.2 5.2S3.8 12 3.8 12Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <circle cx="12" cy="12" r="2.4" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export function EyeOffIcon({ className = "secret-toggle-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24">
      <path
        d="m4.5 4.5 15 15"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M8.8 6.2a8.5 8.5 0 0 1 3.2-.6c5.2 0 8.2 5.2 8.2 5.2a15 15 0 0 1-2.2 2.8M14.2 16a8.6 8.6 0 0 1-2.2.3c-5.2 0-8.2-5.2-8.2-5.2a14.5 14.5 0 0 1 3-3.4"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
      <path
        d="M10.3 10.3a2.4 2.4 0 0 0 3.4 3.4"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function LightningIcon() {
  return (
    <svg aria-hidden="true" className="settings-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="M13 2 5 13h6l-1 9 9-13h-6l1-7Z"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
      />
    </svg>
  );
}

export function CheckIcon() {
  return (
    <svg aria-hidden="true" className="settings-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="m5 12 4.2 4.2L19 6.8"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.4"
      />
    </svg>
  );
}

export function ChevronLeftIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24">
      <path
        d="m15 5-7 7 7 7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.8"
      />
    </svg>
  );
}

export function ChevronRightIcon({ className = "settings-action-icon" }: IconProps = {}) {
  return (
    <svg aria-hidden="true" className={className} fill="none" viewBox="0 0 24 24">
      <path
        d="m9 5 7 7-7 7"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.8"
      />
    </svg>
  );
}

export function XIcon() {
  return (
    <svg aria-hidden="true" className="settings-action-icon" fill="none" viewBox="0 0 24 24">
      <path
        d="m6 6 12 12M18 6 6 18"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2.4"
      />
    </svg>
  );
}
