export const prettyJson = (value: unknown) => JSON.stringify(value ?? {}, null, 2);

export function parseJsonBlock<T>(input: string): T {
  return JSON.parse(input) as T;
}
