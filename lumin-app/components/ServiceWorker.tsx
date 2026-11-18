'use client';

import { useEffect } from 'react';
import { listenForNativeTaps } from '@/lib/push';
import { BRAND } from '@/lib/brand';

// Registers the tiny service worker that lets the app appear in Android's share sheet once installed.
export function ServiceWorker() {
  useEffect(() => {
    if ('serviceWorker' in navigator) navigator.serviceWorker.register(`/sw.js?name=${encodeURIComponent(BRAND.name)}`).catch(() => {});
    listenForNativeTaps(); // only does anything inside the native app
  }, []);
  return null;
}
