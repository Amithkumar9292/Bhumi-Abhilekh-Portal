/**
 * Turn anything thrown by an API call into a message worth showing a user.
 *
 * FastAPI reports problems as `detail`, which is a string for most errors but a
 * list of per-field objects for 422 validation failures, so both shapes are
 * unwrapped here. Falls back to the status code, then the Error message, so we
 * never surface a bare "unknown error".
 */
export function describeApiError(err: unknown): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const { response } = err as { response?: { data?: { detail?: unknown }; status?: number } };
    const detail = response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
    }
    if (response?.status) return `Request failed (HTTP ${response.status}).`;
  }
  if (err instanceof Error) return err.message;
  return 'Something went wrong. Please try again.';
}
