/**
 * Simple 'cn' utility for conditional class names.
 * Replaces clsx and tailwind-merge with a basic implementation 
 * to avoid dependency installation issues in this environment.
 */
export function cn(...inputs: any[]) {
  return inputs
    .filter(Boolean)
    .map((input) => {
      if (typeof input === 'string') return input;
      if (typeof input === 'object' && !Array.isArray(input)) {
        return Object.entries(input)
          .filter(([_, value]) => Boolean(value))
          .map(([key]) => key)
          .join(' ');
      }
      return '';
    })
    .join(' ');
}
