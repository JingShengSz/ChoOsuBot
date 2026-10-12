import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const require = createRequire(new URL('./package.json', import.meta.url));
export async function resolve(specifier, context, nextResolve) {
  if (specifier === 'onnxruntime-common') {
    return {url: pathToFileURL(require.resolve(specifier)).href, shortCircuit: true};
  }
  return nextResolve(specifier, context);
}
