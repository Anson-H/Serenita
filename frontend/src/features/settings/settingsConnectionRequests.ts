
type ConnectionTestRequestIdsRef = {
  current: Map<string, number>;
};

export function beginConnectionTestRequest(
  requestIdsRef: ConnectionTestRequestIdsRef,
  providerId: string
) {
  const requestId = (requestIdsRef.current.get(providerId) ?? 0) + 1;
  requestIdsRef.current.set(providerId, requestId);
  return requestId;
}

export function invalidateConnectionTestRequest(
  requestIdsRef: ConnectionTestRequestIdsRef,
  providerId: string
) {
  beginConnectionTestRequest(requestIdsRef, providerId);
}

export function connectionTestRequestIsCurrent(
  requestIdsRef: ConnectionTestRequestIdsRef,
  providerId: string,
  requestId: number
) {
  return requestIdsRef.current.get(providerId) === requestId;
}
