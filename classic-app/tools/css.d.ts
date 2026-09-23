// Metro/Expo Router's web bundler handles CSS imports at build time; TS just needs to know the
// import is valid. expo/types/global.d.ts declares this too, but that file isn't pulled in without
// the auto-generated expo-env.d.ts reference, so it's declared directly here instead.
declare module '*.css';
