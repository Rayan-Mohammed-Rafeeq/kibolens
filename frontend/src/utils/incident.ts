import type { IncidentSeverity, IncidentStatus } from '../types/incident';

export function getSeverityColor(severity: IncidentSeverity): string {
  switch (severity) {
    case 'CRITICAL':
      return 'text-red-600 bg-red-50';
    case 'HIGH':
      return 'text-orange-600 bg-orange-50';
    case 'WARNING':
      return 'text-yellow-600 bg-yellow-50';
    case 'INFO':
      return 'text-blue-600 bg-blue-50';
    default:
      return 'text-gray-600 bg-gray-50';
  }
}

export function getStatusColor(status: IncidentStatus): string {
  switch (status) {
    case 'DETECTED':
      return 'text-red-600 bg-red-50';
    case 'INVESTIGATING':
      return 'text-orange-600 bg-orange-50';
    case 'IDENTIFIED':
      return 'text-yellow-600 bg-yellow-50';
    case 'RESOLVING':
      return 'text-blue-600 bg-blue-50';
    case 'RESOLVED':
      return 'text-green-600 bg-green-50';
    case 'CLOSED':
      return 'text-gray-600 bg-gray-50';
    default:
      return 'text-gray-600 bg-gray-50';
  }
}

export function formatIncidentNumber(number: string): string {
  return number;
}

export function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp);
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

export function getRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  
  return formatTimestamp(timestamp);
}
