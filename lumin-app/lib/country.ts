// Countries for the pickup address: a full list (two-letter ISO codes, which is what courier APIs take) and a best guess at the
// person's own country so the form starts on the right one. No permission prompt and no outside service: the guess comes from
// the phone's time zone, then its language region, and falls back to the USA.

const CODES =
  'AF AL DZ AD AO AG AR AM AU AT AZ BS BH BD BB BY BE BZ BJ BT BO BA BW BR BN BG BF BI KH CM CA CV CF TD CL CN CO KM CG CD CR CI HR CU CY CZ DK DJ DM DO EC EG SV GQ ER EE SZ ET FJ FI FR GA GM GE DE GH GR GD GT GN GW GY HT HN HK HU IS IN ID IR IQ IE IL IT JM JP JO KZ KE KI KW KG LA LV LB LS LR LY LI LT LU MO MG MW MY MV ML MT MH MR MU MX FM MD MC MN ME MA MZ MM NA NR NP NL NZ NI NE NG MK NO OM PK PW PA PG PY PE PH PL PT QA RO RU RW KN LC VC WS SM ST SA SN RS SC SL SG SK SI SB SO ZA KR SS ES LK SD SR SE CH SY TW TJ TZ TH TL TG TO TT TN TR TM TV UG UA AE GB US UY UZ VU VA VE VN YE ZM ZW'.split(
    ' ',
  );

export const DEFAULT_COUNTRY = 'US';

function nameOf(code: string): string {
  try {
    return new Intl.DisplayNames(['en'], { type: 'region' }).of(code) ?? code;
  } catch {
    return code;
  }
}

// NEXT_PUBLIC_LAUNCH_COUNTRIES=NG (the same as the server's LAUNCH_COUNTRIES): the only countries open for now. Empty = all.
export const LAUNCH_COUNTRIES: string[] = (process.env.NEXT_PUBLIC_LAUNCH_COUNTRIES ?? '')
  .split(',')
  .map((c) => c.trim().toUpperCase())
  .filter((c) => /^[A-Z]{2}$/.test(c));

const OPEN = (code: string) => LAUNCH_COUNTRIES.length === 0 || LAUNCH_COUNTRIES.includes(code);

// Every country we are open in (all of them unless launch is limited), A to Z by name.
export const pickupCountries: { code: string; name: string }[] = CODES.filter(OPEN)
  .map((code) => ({ code, name: nameOf(code) }))
  .sort((a, b) => a.name.localeCompare(b.name));

const KNOWN = new Set(CODES);

// Time zone -> country, for the zones where the zone name alone settles it (all of Africa, plus the UK/Ireland and the US).
const ZONES: Record<string, string> = {
  'Africa/Lagos': 'NG', 'Africa/Accra': 'GH', 'Africa/Nairobi': 'KE', 'Africa/Johannesburg': 'ZA', 'Africa/Kampala': 'UG',
  'Africa/Dar_es_Salaam': 'TZ', 'Africa/Kigali': 'RW', 'Africa/Abidjan': 'CI', 'Africa/Dakar': 'SN', 'Africa/Douala': 'CM',
  'Africa/Cairo': 'EG', 'Africa/Casablanca': 'MA', 'Africa/Addis_Ababa': 'ET', 'Africa/Algiers': 'DZ', 'Africa/Tunis': 'TN',
  'Africa/Lusaka': 'ZM', 'Africa/Harare': 'ZW', 'Africa/Maputo': 'MZ', 'Africa/Luanda': 'AO', 'Africa/Windhoek': 'NA',
  'Africa/Gaborone': 'BW', 'Africa/Kinshasa': 'CD', 'Africa/Lubumbashi': 'CD', 'Africa/Bamako': 'ML', 'Africa/Ouagadougou': 'BF',
  'Africa/Niamey': 'NE', 'Africa/Conakry': 'GN', 'Africa/Freetown': 'SL', 'Africa/Monrovia': 'LR', 'Africa/Lome': 'TG',
  'Africa/Porto-Novo': 'BJ', 'Africa/Libreville': 'GA', 'Africa/Brazzaville': 'CG', 'Africa/Khartoum': 'SD', 'Africa/Juba': 'SS',
  'Africa/Mogadishu': 'SO', 'Africa/Djibouti': 'DJ', 'Africa/Asmara': 'ER', 'Africa/Blantyre': 'MW', 'Africa/Maseru': 'LS',
  'Africa/Mbabane': 'SZ', 'Africa/Banjul': 'GM', 'Africa/Nouakchott': 'MR', 'Africa/Ndjamena': 'TD', 'Africa/Bangui': 'CF',
  'Africa/Bujumbura': 'BI', 'Africa/Tripoli': 'LY', 'Indian/Mauritius': 'MU', 'Indian/Antananarivo': 'MG',
  'Europe/London': 'GB', 'Europe/Dublin': 'IE',
  'America/New_York': 'US', 'America/Chicago': 'US', 'America/Denver': 'US', 'America/Los_Angeles': 'US', 'America/Phoenix': 'US',
  'America/Anchorage': 'US', 'America/Detroit': 'US', 'Pacific/Honolulu': 'US',
};

// Best guess at where this person is. Never asks for location permission; never throws.
export function detectCountry(): string {
  const found = guessCountry();
  if (OPEN(found)) return found;
  return LAUNCH_COUNTRIES[0] ?? DEFAULT_COUNTRY; // a guess outside the countries we are open in starts on the first one that is
}

function guessCountry(): string {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (zone && ZONES[zone]) return ZONES[zone];
    const langs = typeof navigator !== 'undefined' ? [...(navigator.languages ?? []), navigator.language] : [];
    for (const lang of langs) {
      const region = lang?.split('-')[1]?.toUpperCase();
      if (region && KNOWN.has(region)) return region;
    }
  } catch {
    /* fall through to the default */
  }
  return DEFAULT_COUNTRY;
}

// "NG" -> "Nigeria" for showing a saved code; anything that is not a known code (an older free-text country) is shown as it is.
export function countryName(code: string | undefined | null): string {
  const c = (code ?? '').trim();
  return KNOWN.has(c.toUpperCase()) ? nameOf(c.toUpperCase()) : c;
}
