import { Redirect } from 'expo-router';
// Always lands on the landing page first; Gate (app/_layout.tsx) immediately forwards a signed-in
// user on to their real home from there, so this one redirect target works for both cases.
export default function Index() { return <Redirect href="/(auth)/landing" />; }
