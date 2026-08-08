/**
 * Run independent promises together without one denial/failure taking the
 * rest down with it (the failure mode of a plain `Promise.all` when one
 * branch is a 403-denied API call). Each slot resolves to its value on
 * success or `undefined` on failure; `onError` is called per failed slot so
 * callers can toast or log without losing the others.
 */
export async function settleAll<T extends readonly unknown[]>(
  promises: readonly [...{ [K in keyof T]: Promise<T[K]> }],
  onError?: (index: number, error: unknown) => void,
): Promise<{ [K in keyof T]: T[K] | undefined }> {
  const results = await Promise.allSettled(promises);
  return results.map((result, index) => {
    if (result.status === 'fulfilled') {
      return result.value;
    }
    onError?.(index, result.reason);
    return undefined;
  }) as { [K in keyof T]: T[K] | undefined };
}
