import type { FieldErrors, Resolver } from "react-hook-form";
import type { z } from "zod";

/**
 * 轻量 zod resolver（不引入 @hookform/resolvers）：
 * 把 zod safeParse 的结果转换成 react-hook-form 的 Resolver 输出。
 */
export function zodResolver<T extends z.ZodObject<z.ZodRawShape>>(
  schema: T,
): Resolver<z.infer<T>> {
  return ((values: unknown) => {
    const result = schema.safeParse(values);
    if (result.success) {
      return { values: result.data as z.infer<T>, errors: {} as FieldErrors };
    }
    const errors: FieldErrors = {};
    for (const issue of result.error.issues) {
      const path = issue.path.join(".") || "_root";
      const current = errors as Record<string, { type: string; message: string }>;
      if (!current[path]) {
        current[path] = { type: issue.code, message: issue.message };
      }
    }
    return { values: {} as z.infer<T>, errors };
  }) as unknown as Resolver<z.infer<T>>;
}
