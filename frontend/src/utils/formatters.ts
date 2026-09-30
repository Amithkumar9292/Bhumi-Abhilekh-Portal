import { formatDistanceToNow, format } from 'date-fns';
import { enIN } from 'date-fns/locale';

export function formatRelative(iso: string): string {
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: enIN });
  } catch {
    return iso;
  }
}

export function formatDate(iso: string): string {
  try { return format(new Date(iso), 'd MMM yyyy'); } catch { return iso; }
}

export function formatDateTime(iso: string): string {
  try { return format(new Date(iso), 'd MMM yyyy, HH:mm'); } catch { return iso; }
}

export function formatArea(ha: number): string {
  return `${ha.toFixed(4)} ha`;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const STATUS_LABELS: Record<string, string> = {
  PENDING:      'Pending',
  UNDER_REVIEW: 'Under Review',
  VERIFIED:     'Verified',
  REJECTED:     'Rejected',
  ARCHIVED:     'Archived',
};

export const LAND_USE_LABELS: Record<string, string> = {
  AGRICULTURAL: 'Agricultural',
  RESIDENTIAL:  'Residential',
  COMMERCIAL:   'Commercial',
  FOREST:       'Forest',
  INDUSTRIAL:   'Industrial',
  WASTELAND:    'Wasteland',
};

// ── Language-aware Intl locale mapping ─────────────────────────────────────────

const LANG_TO_INTL: Record<string, string> = {
  en: 'en-IN', hi: 'hi-IN', bn: 'bn-IN', te: 'te-IN', mr: 'mr-IN',
  ta: 'ta-IN', gu: 'gu-IN', kn: 'kn-IN', ml: 'ml-IN', pa: 'pa-IN',
  ur: 'ur-IN', or: 'or-IN', as: 'as-IN', mai: 'hi-IN', sa: 'hi-IN',
};

/**
 * Convert our app language code to a valid Intl locale string.
 * Usage: new Date().toLocaleDateString(getIntlLocale('hi'), ...)
 */
export function getIntlLocale(langCode: string): string {
  return LANG_TO_INTL[langCode] ?? 'en-IN';
}

/**
 * Format a number using Intl.NumberFormat with the given lang.
 */
export function formatNumber(value: number, langCode: string = 'en'): string {
  return new Intl.NumberFormat(getIntlLocale(langCode)).format(value);
}
