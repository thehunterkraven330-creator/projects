'use client';

import { createContext, useContext } from 'react';
import type { Product } from './types';

// What the story player needs from the app around it: open a tagged product, add it to the cart.
export interface StoryActions {
  // returnHere: keep the Updates screen and player where they are (hidden) so Back on the product lands on them again.
  openProduct: (product: Product, opts?: { returnHere?: boolean }) => void;
  addToCart: (product: Product, color: string, size: string) => void;
  openLive: () => void;
  // Go to the live a seller is hosting right now: 'watching' (it is open), 'not_live' (they are not live), 'failed' (could not check).
  watchLiveOf: (hostId: string) => Promise<'watching' | 'not_live' | 'failed'>;
  openStories: () => void;
  // Open someone's profile (from the list of who saw an update).
  // returnHere: keep the Updates screen and player where they are (hidden) so Back on the profile lands on the list again.
  openPoster: (person: { id: string; name: string; avatar?: string | null }, opts?: { returnHere?: boolean }) => void;
  layersHidden: boolean; // the Updates screen and player are tucked away while a profile is shown over them
}
export const StoryActionsContext = createContext<StoryActions | null>(null);
export const useStoryActions = () => useContext(StoryActionsContext);
