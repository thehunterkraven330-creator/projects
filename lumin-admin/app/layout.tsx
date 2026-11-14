import type { Metadata } from 'next';
import './globals.css';
import { APP_NAME } from '@/lib/brand';
import { ErrorReporter } from '@/components/ErrorReporter';

export const metadata: Metadata = {
  title: `${APP_NAME} Admin`,
  description: `Moderation, disputes, and analytics for the ${APP_NAME} platform`,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-panel font-sans text-text antialiased">
        <ErrorReporter />
        {children}
      </body>
    </html>
  );
}
