import type { Metadata } from 'next'
import { ThemeProvider } from '@/components/theme-provider'
import './globals.css'

export const metadata: Metadata = {
  title: 'HoFi Protocol — Care Economy Dashboard',
  description: 'Holistic Finance: making care work visible, measurable, and rewarded on-chain. The act of caring is the yield.',
  openGraph: {
    title: 'HoFi Protocol',
    description: 'The act of caring is the yield.',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  )
}
