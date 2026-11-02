import { GatewayTriggerForm } from '../forms/GatewayTriggerForm';

/** The WhatsApp message trigger: the shared chat trigger form with WhatsApp's options and wording. */
export const WhatsAppTriggerForm = ({ nodeId }: { nodeId: string }) => <GatewayTriggerForm nodeId={nodeId} kind="whatsapp" />;
