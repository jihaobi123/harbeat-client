import React from 'react'

interface Props {
  children: React.ReactNode
  fallback?: React.ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info)
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="flex flex-col items-center justify-center h-full text-slate-400 p-8">
          <p className="text-red-400 text-sm mb-2">组件渲染出错</p>
          <p className="text-xs text-slate-500 text-center max-w-md">
            {this.state.error?.message}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-4 px-4 py-1.5 bg-primary/20 text-primary rounded-lg text-xs hover:bg-primary/30 transition-colors"
          >
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
