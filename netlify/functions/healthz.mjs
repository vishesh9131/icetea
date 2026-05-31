import { proxyToBackend } from './_proxy.mjs'

export default async (request) => proxyToBackend(request)

export const config = {
  path: '/healthz',
}
