/**
 * Formats a date string or Date object into a human-readable "time ago" string
 * Examples: "5 mins ago", "2 hours ago", "3 days ago", "2 weeks ago", "1 month ago"
 * 
 * @param date - Date string or Date object
 * @returns Human-readable time ago string, or "Never" if date is invalid/null
 */
export function formatTimeAgo(date: string | Date | null | undefined): string {
  if (!date) return 'Never';
  
  try {
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    
    // Check if date is valid
    if (isNaN(dateObj.getTime())) {
      return 'Never';
    }
    
    const now = new Date();
    const diffInMs = now.getTime() - dateObj.getTime();
    const diffInSeconds = Math.floor(diffInMs / 1000);
    const diffInMinutes = Math.floor(diffInSeconds / 60);
    const diffInHours = Math.floor(diffInMinutes / 60);
    const diffInDays = Math.floor(diffInHours / 24);
    const diffInWeeks = Math.floor(diffInDays / 7);
    const diffInMonths = Math.floor(diffInDays / 30);
    const diffInYears = Math.floor(diffInDays / 365);
    
    // Handle future dates
    if (diffInMs < 0) {
      return 'Just now';
    }
    
    // Less than a minute
    if (diffInSeconds < 60) {
      return 'Just now';
    }
    
    // Less than an hour
    if (diffInMinutes < 60) {
      return `${diffInMinutes} ${diffInMinutes === 1 ? 'min' : 'mins'} ago`;
    }
    
    // Less than a day
    if (diffInHours < 24) {
      return `${diffInHours} ${diffInHours === 1 ? 'hour' : 'hours'} ago`;
    }
    
    // Less than a week
    if (diffInDays < 7) {
      return `${diffInDays} ${diffInDays === 1 ? 'day' : 'days'} ago`;
    }
    
    // Less than a month
    if (diffInWeeks < 4) {
      return `${diffInWeeks} ${diffInWeeks === 1 ? 'week' : 'weeks'} ago`;
    }
    
    // Less than a year
    if (diffInMonths < 12) {
      return `${diffInMonths} ${diffInMonths === 1 ? 'month' : 'months'} ago`;
    }
    
    // Years
    return `${diffInYears} ${diffInYears === 1 ? 'year' : 'years'} ago`;
  } catch {
    return 'Never';
  }
}

/**
 * Calculate duration between start_time and end_time
 * Returns duration in seconds or minutes, or "Not available" if invalid
 */
export function calculateDuration(
  startTime: string | null | undefined,
  endTime: string | null | undefined
): string {
  if (!startTime || !endTime) {
    return 'Not available';
  }

  try {
    const start = new Date(startTime);
    const end = new Date(endTime);

    // Check if dates are valid
    if (isNaN(start.getTime()) || isNaN(end.getTime())) {
      return 'Not available';
    }

    const diffInMs = end.getTime() - start.getTime();

    // Handle negative duration (end before start)
    if (diffInMs < 0) {
      return 'Not available';
    }

    const diffInSeconds = Math.floor(diffInMs / 1000);
    const diffInMinutes = Math.floor(diffInSeconds / 60);

    // If less than 60 seconds, show in seconds
    if (diffInSeconds < 60) {
      return `${diffInSeconds}s`;
    }

    // Otherwise show in minutes with seconds
    const remainingSeconds = diffInSeconds % 60;
    if (remainingSeconds === 0) {
      return `${diffInMinutes}m`;
    }
    return `${diffInMinutes}m ${remainingSeconds}s`;
  } catch {
    return 'Not available';
  }
}

