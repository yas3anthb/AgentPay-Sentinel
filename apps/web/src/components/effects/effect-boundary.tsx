"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Rendered instead of the crashed child. Defaults to nothing — the calm
   * background colour underneath already stands on its own. */
  fallback?: ReactNode;
  /** Optional hook for a caller that needs to react to the crash beyond
   * swapping in a fallback node — e.g. reverting a view toggle so the UI
   * doesn't keep offering a control for a view that just proved broken. */
  onError?: () => void;
}

interface State {
  crashed: boolean;
}

/**
 * Scoped tightly around a single decorative visual effect — never around a
 * whole page. A background animation is allowed to fail; it is never allowed
 * to take the rest of the page down with it.
 *
 * This exists independently of whatever the current root cause of a given
 * WebGL crash turns out to be. Effects like this wrap third-party rendering
 * code we do not fully control (vendored components, transitive Three.js
 * dependency versions); the boundary is the backstop for the next
 * incompatibility, not just the one that prompted adding it.
 */
export class EffectBoundary extends Component<Props, State> {
  state: State = { crashed: false };

  static getDerivedStateFromError(): State {
    return { crashed: true };
  }

  componentDidCatch(error: unknown, info: unknown) {
    // eslint-disable-next-line no-console
    console.error("Decorative effect crashed; falling back silently.", error, info);
    this.props.onError?.();
  }

  render() {
    if (this.state.crashed) return this.props.fallback ?? null;
    return this.props.children;
  }
}
