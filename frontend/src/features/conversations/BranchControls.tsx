import { ChevronLeftIcon, ChevronRightIcon } from "../../components/icons";

type BranchControlsProps = {
  currentIndex: number;
  onSwitch: (direction: -1 | 1) => void;
  siblingCount: number;
};

export function BranchControls({ currentIndex, onSwitch, siblingCount }: BranchControlsProps) {
  if (siblingCount < 2) {
    return null;
  }

  return (
    <div className="branch-controls">
      <button
        aria-label="切换到上一条分支"
        disabled={currentIndex <= 0}
        onClick={() => onSwitch(-1)}
        type="button"
      >
        <ChevronLeftIcon className="message-action-icon" />
      </button>
      <span>
        {currentIndex + 1}/{siblingCount}
      </span>
      <button
        aria-label="切换到下一条分支"
        disabled={currentIndex >= siblingCount - 1}
        onClick={() => onSwitch(1)}
        type="button"
      >
        <ChevronRightIcon className="message-action-icon" />
      </button>
    </div>
  );
}
