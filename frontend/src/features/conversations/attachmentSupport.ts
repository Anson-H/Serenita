export type AttachmentModel = {
  file_mime_types: string[];
} | null | undefined;

export type AttachmentResource = {
  mime_type: string;
};

export function modelFileMimeTypes(model: AttachmentModel) {
  return model?.file_mime_types ?? [];
}

export function mergeModelFileMimeTypes(...models: AttachmentModel[]) {
  return Array.from(
    new Set(models.flatMap((model) => modelFileMimeTypes(model)))
  );
}

export function canAttachFilesForScenario(activeScenario: string, mimeTypes: string[]) {
  return activeScenario === "home" && mimeTypes.length > 0;
}

export function filterResourcesByMimeTypes<T extends AttachmentResource>(resources: T[], mimeTypes: string[]) {
  if (!resources.length) {
    return resources;
  }
  const supportedMimeTypes = new Set(mimeTypes);
  return resources.filter((resource) => supportedMimeTypes.has(resource.mime_type));
}
