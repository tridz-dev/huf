import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';

export interface GatewayTemplate {
  name: string;
  gateway: string;
  template_type: string;
  template_name: string;
  external_id?: string;
  category: string;
  language: string;
  status: string;
  components?: string;
  quality_rating?: string;
  last_synced_on?: string;
}

export interface GatewayTemplateComponent {
  type: 'HEADER' | 'BODY' | 'FOOTER' | 'BUTTONS';
  text?: string;
  example?: {
    body_text?: string[][];
  };
  format?: string;
  buttons?: Array<{
    type: string;
    text: string;
    url?: string;
  }>;
}

export async function listGatewayTemplates(gateway: string): Promise<GatewayTemplate[]> {
  try {
    const response = await call.get('huf.ai.gateway_service.list_gateway_templates', {
      gateway,
    });
    return (response.message ?? response) as GatewayTemplate[];
  } catch (err: any) {
    if (err.message?.includes('ValidationError') || err.exc?.includes('ValidationError')) {
      throw new Error('This provider does not support templates');
    }
    throw err;
  }
}

export async function pushGatewayTemplate(name: string): Promise<GatewayTemplate> {
  const response = await call.post('huf.ai.gateway_service.push_gateway_template', {
    name,
  });
  return (response.message ?? response) as GatewayTemplate;
}

export async function syncGatewayTemplate(name: string): Promise<GatewayTemplate> {
  const response = await call.post('huf.ai.gateway_service.sync_gateway_template', {
    name,
  });
  return (response.message ?? response) as GatewayTemplate;
}

export async function deleteGatewayTemplate(name: string): Promise<void> {
  await db.deleteDoc('Gateway Template', name);
}

export async function createGatewayTemplate(data: Partial<GatewayTemplate>): Promise<GatewayTemplate> {
  return (await db.createDoc('Gateway Template', data)) as GatewayTemplate;
}

export async function updateGatewayTemplate(name: string, data: Partial<GatewayTemplate>): Promise<GatewayTemplate> {
  return (await db.updateDoc('Gateway Template', name, data)) as GatewayTemplate;
}
