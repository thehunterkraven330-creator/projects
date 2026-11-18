'use client';

import { useEffect } from 'react';
import { installErrorReporting } from '@/lib/errorReport';

// Switches on error reporting for the whole app (mounted once in the layout). Renders nothing.
export function ErrorReporter() {
  useEffect(() => installErrorReporting(), []);
  return null;
}
