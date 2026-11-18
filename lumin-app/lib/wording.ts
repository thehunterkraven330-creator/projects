// Words the app uses in more than one place, so changing one here changes it everywhere.
//
// SEARCHED_WORD is the word after the number on the Found it screen ("45 Searches") and in the hover text of the search count
// on profile tiles. Change the text below to the word you want, for example 'Scans' or 'Finds', and rebuild.
// Or set NEXT_PUBLIC_SEARCHED_WORD on the website service and redeploy; the variable wins when set.
const SEARCHED_WORD_DEFAULT = 'Searches';

export const SEARCHED_WORD = (process.env.NEXT_PUBLIC_SEARCHED_WORD || '').trim() || SEARCHED_WORD_DEFAULT;
