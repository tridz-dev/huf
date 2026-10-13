/**
 * Chess Agent API
 *
 * Thin wrapper around the HUF Agent integration for chess move requests.
 * Sends the current board state, move history, and legal moves to the
 * HUF Chess Player agent and parses the response.
 *
 * Returns null on any failure (network, parse, invalid move) without throwing,
 * allowing the game orchestration layer to decide on retry/repair.
 */

import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

export interface RequestAgentMoveParams {
	fen: string;
	history: string;
	legalMoves: string[];
	color: 'white' | 'black';
}

export interface AgentMoveResponse {
	move: string;
	comment?: string;
}

/**
 * Request the chess agent to play a move.
 *
 * Builds a per-turn prompt with the FEN, move history, legal moves, and current color,
 * sends it to the HUF Chess Player agent via run_agent_sync, and parses the response.
 *
 * Returns { move, comment } on success, or null if the agent fails to respond or
 * returns an invalid move.
 */
export async function requestAgentMove(
	params: RequestAgentMoveParams,
): Promise<AgentMoveResponse | null> {
	try {
		const prompt = buildChessPrompt(params);

		const response = await call.post('huf.ai.agent_integration.run_agent_sync', {
			agent_name: 'HUF Chess Player',
			prompt,
			response_format: { type: 'json_object' },
			now: true,
		});

		// Gate on success === true (direct-execution path has no status key)
		if (!response.message || response.message.success !== true) {
			return null;
		}

		// Prefer structured response (already JSON-parsed server-side)
		if (response.message.structured) {
			const structured = response.message.structured;
			if (typeof structured.move === 'string' && structured.move.length > 0) {
				return {
					move: structured.move,
					comment: structured.comment || undefined,
				};
			}
		}

		// Fallback: scan raw response text for a substring match against legalMoves
		if (response.message.response && typeof response.message.response === 'string') {
			const responseText = response.message.response;
			for (const legalMove of params.legalMoves) {
				if (responseText.includes(legalMove)) {
					return { move: legalMove };
				}
			}
		}

		// No valid move found in response
		return null;
	} catch (error) {
		handleFrappeError(error);
		return null;
	}
}

/**
 * Build the per-turn prompt for the chess agent.
 *
 * Format per spec §5:
 * You are playing {color}.
 * FEN: {fen}
 * Moves so far: {history}
 * Legal moves: {JSON array of legal SAN moves}
 *
 * Return only:
 * {"move": "<one exact move from legal_moves>", "comment": "<optional short comment>"}
 */
function buildChessPrompt(params: RequestAgentMoveParams): string {
	const { fen, history, legalMoves, color } = params;

	return `You are playing ${color}.
FEN: ${fen}
Moves so far: ${history}
Legal moves: ${JSON.stringify(legalMoves)}

Return only:
{"move": "<one exact move from legal_moves>", "comment": "<optional short comment>"}`;
}
