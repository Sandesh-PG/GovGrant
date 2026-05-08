import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface StatusBadgeProps {
  score: number;
  className?: string;
}

export function StatusBadge({ score, className }: StatusBadgeProps) {
  let colorClass = 'bg-red-100 text-red-700 border-red-200';
  if (score >= 70) {
    colorClass = 'bg-green-100 text-green-700 border-green-200';
  } else if (score >= 50) {
    colorClass = 'bg-amber-100 text-amber-700 border-amber-200';
  }

  return (
    <span
      className={cn(
        'px-2 py-0.5 rounded-full text-xs font-semibold border',
        colorClass,
        className
      )}
    >
      {score}% Match
    </span>
  );
}
