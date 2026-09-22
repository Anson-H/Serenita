type ConnectionTestRequestsRef = {
  current: Map<string, AbortController>;
};

export function beginConnectionTestRequest(
  requestsRef: ConnectionTestRequestsRef,
  providerId: string
) {
  invalidateConnectionTestRequest(requestsRef, providerId);
  const request = new AbortController();
  requestsRef.current.set(providerId, request);
  return request;
}

export function invalidateConnectionTestRequest(
  requestsRef: ConnectionTestRequestsRef,
  providerId: string
) {
  requestsRef.current.get(providerId)?.abort();
  requestsRef.current.delete(providerId);
}

export function connectionTestRequestIsCurrent(
  requestsRef: ConnectionTestRequestsRef,
  providerId: string,
  request: AbortController
) {
  return requestsRef.current.get(providerId) === request;
}
