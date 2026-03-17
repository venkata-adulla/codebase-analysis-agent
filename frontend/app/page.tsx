import Link from 'next/link'

export default function Home() {
  return (
    <main className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-4xl font-bold mb-8">Codebase Analysis Agent</h1>
        <p className="text-lg mb-8 text-gray-600 dark:text-gray-400">
          AI-powered codebase analysis and dependency mapping system
        </p>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Link
            href="/dashboard"
            className="p-6 border rounded-lg hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">Dashboard</h2>
            <p className="text-gray-600 dark:text-gray-400">
              Overview of analyzed repositories and services
            </p>
          </Link>
          
          <Link
            href="/dependency-graph"
            className="p-6 border rounded-lg hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">Dependency Graph</h2>
            <p className="text-gray-600 dark:text-gray-400">
              Interactive visualization of service dependencies
            </p>
          </Link>
          
          <Link
            href="/services"
            className="p-6 border rounded-lg hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">Service Inventory</h2>
            <p className="text-gray-600 dark:text-gray-400">
              Catalog of all services with documentation
            </p>
          </Link>
          
          <Link
            href="/impact-analysis"
            className="p-6 border rounded-lg hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">Impact Analysis</h2>
            <p className="text-gray-600 dark:text-gray-400">
              Change impact visualization and recommendations
            </p>
          </Link>
          
          <Link
            href="/agent-status"
            className="p-6 border rounded-lg hover:shadow-lg transition-shadow"
          >
            <h2 className="text-xl font-semibold mb-2">Agent Status</h2>
            <p className="text-gray-600 dark:text-gray-400">
              Real-time agent execution status
            </p>
          </Link>
        </div>
      </div>
    </main>
  )
}
