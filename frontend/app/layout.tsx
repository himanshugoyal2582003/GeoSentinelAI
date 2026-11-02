import "./globals.css";

export const metadata = {
  title: "GeoSentinel AI",
  description: "Satellite-based land-change monitoring command center",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
