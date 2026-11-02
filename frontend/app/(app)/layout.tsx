import { Suspense } from "react";
import { AppShell } from "@/components/app/shell";

export default function Layout({ children }: { children: React.ReactNode }) {
  // the shell reads the URL (usePathname/useParams), which is only known at request time
  return <Suspense><AppShell>{children}</AppShell></Suspense>;
}
