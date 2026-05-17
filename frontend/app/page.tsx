import { redirect } from "next/navigation";

// Raiz sempre joga para login (o middleware decide o resto)
export default function Home() {
  redirect("/login");
}
