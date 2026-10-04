import { runtimeKind } from "./api";
import type { RuntimeKind } from "./types";

/**
 * A link that asks a conversation's questions again: `/?q=…&q=…&rt=recorded|live`,
 * one `q` per message, in order. A follow-up ("remove Apple") means nothing
 * without the questions before it, so the link carries them all. It holds the
 * messages only, never a thread, so opening it starts a new conversation and no
 * visitor's state travels in the URL (ADR 0006 keeps threads private).
 */
export interface SharedQuestions {
  questions: string[];
  /** null: the deployment's default runtime. */
  runtime: RuntimeKind | null;
}

/** A shared link asks at most this many messages, so it cannot run a thread out of turns. */
export const MAX_SHARED_MESSAGES = 8;

export function shareLink(origin: string, messages: string[], runtime: RuntimeKind | null): string {
  const params = new URLSearchParams();
  for (const message of messages.slice(-MAX_SHARED_MESSAGES)) params.append("q", message.trim());
  if (runtime) params.set("rt", runtime);
  return `${origin}/?${params.toString()}`;
}

/**
 * The questions a page was opened to ask, or null when any is one the composer
 * would not take: a conversation asked with a message missing would answer
 * another question.
 */
export function parseShareLink(search: string, maxChars: number): SharedQuestions | null {
  const params = new URLSearchParams(search);
  const questions = params.getAll("q").map((question) => question.trim());
  if (questions.length === 0 || questions.length > MAX_SHARED_MESSAGES) return null;
  if (questions.some((question) => !question || question.length > maxChars)) return null;
  return { questions, runtime: runtimeKind(params.get("rt")) };
}
