import { access } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

export async function resolve(specifier, context, nextResolve) {
  if ((specifier.startsWith("./") || specifier.startsWith("../")) && !path.extname(specifier)) {
    try {
      const parentPath = context.parentURL ? fileURLToPath(context.parentURL) : process.cwd();
      const candidate = path.resolve(path.dirname(parentPath), `${specifier}.ts`);
      await access(candidate);
      return nextResolve(pathToFileURL(candidate).href, context);
    } catch {
      // Fall through to Node's normal resolver.
    }
  }
  return nextResolve(specifier, context);
}
