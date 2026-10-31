import type { GatewayParam, GatewayParamSpec, GatewayParamValue, GatewayTriggerSpec } from './gatewayTrigger.types';

/** True when a stored value says nothing (so the filter is off and the entry can be dropped). */
export function isEmptyParam(value: GatewayParamValue | undefined): boolean {
  return value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0);
}

/** What a control shows: the stored value, else the registry default. */
export function paramValue(params: readonly GatewayParam[] | undefined, spec: GatewayParamSpec): GatewayParamValue {
  const found = params?.find((p) => p.key === spec.key);
  return found ? found.value : spec.default;
}

/**
 * The params list after one control changed. A value equal to the default, or an empty one, removes the entry: the
 * flow only stores what the person actually set, and an empty list is never kept.
 */
/** Equal by contents, so a fresh `[]` or `['a']` array counts as the default it repeats. */
export function sameValue(a: GatewayParamValue | undefined, b: GatewayParamValue | undefined): boolean {
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => x === b[i]);
  return a === b;
}

export function withParam(params: readonly GatewayParam[] | undefined, spec: GatewayParamSpec, value: GatewayParamValue): GatewayParam[] {
  const rest = (params ?? []).filter((p) => p.key !== spec.key);
  if (sameValue(value, spec.default) || isEmptyParam(value)) return rest;
  return [...rest, { key: spec.key, value }];
}

/** Whether `show_when` lets this option show, given what is set now (an unset controlling option counts as its default). */
export function isParamVisible(spec: GatewayTriggerSpec, param: GatewayParamSpec, params: readonly GatewayParam[] | undefined): boolean {
  if (!param.show_when) return true;
  const controller = spec.params.find((p) => p.key === param.show_when!.key);
  const current = controller ? paramValue(params, controller) : params?.find((p) => p.key === param.show_when!.key)?.value;
  return typeof current === 'string' && param.show_when.in.includes(current);
}

/** The options to draw in one section, in registry order, with `show_when` applied. */
export function visibleParams(spec: GatewayTriggerSpec, params: readonly GatewayParam[] | undefined, section: 'setup' | 'more'): GatewayParamSpec[] {
  return spec.params.filter((p) => p.section === section && isParamVisible(spec, p, params));
}

/** Whether a param still holds a non-default value (used to open "More options" when something is set in it). */
export function hasCustomValue(params: readonly GatewayParam[] | undefined, spec: GatewayParamSpec): boolean {
  return !!params?.some((p) => p.key === spec.key && !isEmptyParam(p.value) && !sameValue(p.value, spec.default));
}
