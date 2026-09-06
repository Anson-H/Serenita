import type {
  RemoteModel
} from "../../api/client";

type RemoteModelIdentity = {
  model: string;
  supplier: string;
};

export type RemoteModelSupplierGroup = {
  key: string;
  label: string;
  models: RemoteModel[];
};

const directModelGroupKey = "direct";

export function remoteModelIdentity(remoteModelId: string): RemoteModelIdentity {
  const normalizedId = remoteModelId.trim();
  const separatorIndex = normalizedId.indexOf("/");
  if (separatorIndex <= 0 || separatorIndex === normalizedId.length - 1) {
    return { model: normalizedId, supplier: "" };
  }
  return {
    supplier: normalizedId.slice(0, separatorIndex).trim(),
    model: normalizedId.slice(separatorIndex + 1).trim()
  };
}

function sameModelGroupName(left: string, right: string): boolean {
  return left.localeCompare(right, "zh-CN", { sensitivity: "base" }) === 0;
}

export function groupRemoteModelsBySupplier(
  models: RemoteModel[],
  providerName: string
): RemoteModelSupplierGroup[] {
  const providerGroupName = providerName.trim() || "提供方";
  const groups = new Map<string, RemoteModelSupplierGroup>();
  const newestFirstModels = [...models].sort(
    (left, right) => (right.created_at ?? Number.NEGATIVE_INFINITY)
      - (left.created_at ?? Number.NEGATIVE_INFINITY)
  );

  for (const model of newestFirstModels) {
    const identity = remoteModelIdentity(model.remote_model_id);
    const belongsToProviderGroup = !identity.supplier
      || sameModelGroupName(identity.supplier, providerGroupName);
    const key = !belongsToProviderGroup
      ? `supplier:${identity.supplier.toLocaleLowerCase("zh-CN")}`
      : directModelGroupKey;
    const existingGroup = groups.get(key);
    if (existingGroup) {
      existingGroup.models.push(model);
      continue;
    }
    groups.set(key, {
      key,
      label: belongsToProviderGroup ? providerGroupName : identity.supplier,
      models: [model]
    });
  }

  return [...groups.values()].sort((left, right) => {
    const leftMatchesProvider = left.key === directModelGroupKey
      || sameModelGroupName(left.label, providerGroupName);
    const rightMatchesProvider = right.key === directModelGroupKey
      || sameModelGroupName(right.label, providerGroupName);
    return Number(rightMatchesProvider) - Number(leftMatchesProvider);
  });
}
