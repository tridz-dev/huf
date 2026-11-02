import { GatewayTriggerForm } from '../forms/GatewayTriggerForm';

/** The Telegram message trigger: the shared chat trigger form with Telegram's options and wording. */
export const TelegramTriggerForm = ({ nodeId }: { nodeId: string }) => <GatewayTriggerForm nodeId={nodeId} kind="telegram" />;
