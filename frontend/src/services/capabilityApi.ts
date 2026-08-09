import { call } from "@/lib/frappe-sdk";
import { handleFrappeError } from "@/lib/frappe-error";
import type {
  CapabilityDescriptor,
  CapabilityApp,
  CapabilityResourceDetail,
} from "@/types/capability.types";

/**
 * Fetch all available capability apps
 */
export async function getCapabilityApps(): Promise<CapabilityApp[]> {
  try {
    const result = await call.get("huf.ai.capabilities.api.get_capability_apps");
    return (result?.message || result) as CapabilityApp[];
  } catch (error) {
    handleFrappeError(error, "Error fetching capability apps");
    return [];
  }
}

/**
 * Search app actions by query
 */
export async function searchAppActions(
  app: string,
  query = "",
  limit = 50,
): Promise<CapabilityDescriptor[]> {
  try {
    const result = await call.get("huf.ai.capabilities.api.search_app_actions", {
      app,
      query,
      limit,
    });
    return (result?.message || result) as CapabilityDescriptor[];
  } catch (error) {
    handleFrappeError(error, `Error searching app actions for ${app}`);
    return [];
  }
}

/**
 * Describe a specific app action by capability ID
 */
export async function describeAppAction(capabilityId: string): Promise<CapabilityDescriptor> {
  try {
    const result = await call.get("huf.ai.capabilities.api.describe_app_action", {
      capability_id: capabilityId,
    });
    return (result?.message || result) as CapabilityDescriptor;
  } catch (error) {
    handleFrappeError(error, `Error describing app action ${capabilityId}`);
  }
}

/**
 * Get app resources filtered by scope
 */
export async function getAppResources(
  app: string,
  scope: "recommended" | "discovered" | "all" = "recommended",
): Promise<unknown[]> {
  try {
    const result = await call.get("huf.ai.capabilities.api.get_app_resources", {
      app,
      scope,
    });
    return (result?.message || result) as unknown[];
  } catch (error) {
    handleFrappeError(error, `Error fetching resources for app ${app}`);
    return [];
  }
}

/**
 * Describe a specific resource by app and doctype
 */
export async function describeResource(
  app: string,
  doctype: string,
): Promise<CapabilityResourceDetail> {
  try {
    const result = await call.get("huf.ai.capabilities.api.describe_resource", {
      app,
      doctype,
    });
    return (result?.message || result) as CapabilityResourceDetail;
  } catch (error) {
    handleFrappeError(error, `Error describing resource ${doctype} in app ${app}`);
  }
}

/**
 * Get resource events for a specific doctype
 */
export async function getResourceEvents(
  app: string,
  doctype: string,
  includeAdvanced = false,
): Promise<CapabilityDescriptor[]> {
  try {
    const result = await call.get("huf.ai.capabilities.api.get_resource_events", {
      app,
      doctype,
      include_advanced: includeAdvanced,
    });
    return (result?.message || result) as CapabilityDescriptor[];
  } catch (error) {
    handleFrappeError(error, `Error fetching events for ${doctype} in app ${app}`);
    return [];
  }
}

/**
 * Preview trigger payload for event-based automation
 */
export async function previewTriggerPayload(
  app: string,
  doctype: string,
  eventCapabilityId: string,
  condition?: string,
  promptField?: string,
): Promise<Record<string, unknown>> {
  try {
    const result = await call.get("huf.ai.capabilities.api.preview_trigger_payload", {
      app,
      doctype,
      event_capability_id: eventCapabilityId,
      condition,
      prompt_field: promptField,
    });
    return (result?.message || result) as Record<string, unknown>;
  } catch (error) {
    handleFrappeError(
      error,
      `Error previewing trigger payload for event ${eventCapabilityId}`,
    );
    return {};
  }
}
