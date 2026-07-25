export function isDefaultConversationTitle(title: string): boolean {
  return (
    title.startsWith('Chat with') ||
    title.startsWith('Conversation with') ||
    title.startsWith('Streaming chat with')
  );
}
