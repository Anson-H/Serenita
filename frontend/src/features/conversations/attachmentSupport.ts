type AttachmentResource = { mime_type: string };

export function canAttachFilesForScenario(
  activeScenario: string,
  mimeTypes: string[]
) {
  return (
    (activeScenario === "home" || activeScenario === "reports") &&
    mimeTypes.length > 0
  );
}

export function filterResourcesByMimeTypes<T extends AttachmentResource>(resources: T[], mimeTypes: string[]) {
  if (!resources.length) {
    return resources;
  }
  const supportedMimeTypes = new Set(mimeTypes);
  const filteredResources = resources.filter((resource) => supportedMimeTypes.has(resource.mime_type));
  return filteredResources.length === resources.length ? resources : filteredResources;
}
