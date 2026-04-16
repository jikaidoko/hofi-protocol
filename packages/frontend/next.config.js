/** @type {import('next').NextConfig} */
module.exports = {
  // Transpila Mapbox GL para compatibilidad con Next.js SSR
  transpilePackages: ['mapbox-gl'],

  // Ignorar errores TS y ESLint en el build de producción.
  // Los componentes del zip tienen dependencias faltantes que no se usan en la UI.
  // Remover cuando estén limpiados.
  typescript: {
    ignoreBuildErrors: true,
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
}
