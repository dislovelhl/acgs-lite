import { useCallback, useMemo, useEffect, useState } from "react"
import {
  ReactFlow,
  Background,
  type Node,
  type Edge,
  type NodeProps,
  Position,
  useNodesState,
  useEdgesState,
} from "@xyflow/react"
import dagre from "@dagrejs/dagre"
import "@xyflow/react/dist/style.css"
import type { PipelineStage } from "@/lib/pipeline-types"

const NODE_WIDTH = 200
const NODE_HEIGHT = 120

const STATUS_BORDER: Record<string, string> = {
  healthy: "border-governance/50",
  warning: "border-warning/50",
  critical: "border-destructive/50",
}

const STATUS_GLOW: Record<string, string> = {
  healthy: "",
  warning: "shadow-[0_0_12px_rgba(255,200,50,0.15)]",
  critical: "shadow-[0_0_12px_rgba(255,80,80,0.2)]",
}

function formatMs(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`
  return `${ms.toFixed(2)}ms`
}

function formatCount(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

interface StageNodeData {
  stage: PipelineStage
  selected: boolean
  onSelect: (id: string) => void
  [key: string]: unknown
}

function StageNode({ data }: NodeProps<Node<StageNodeData>>) {
  const { stage, selected, onSelect } = data
  const budgetPct = Math.min((stage.latency.p99_ms / stage.budget_ms) * 100, 100)
  const barColor =
    budgetPct < 60
      ? "bg-governance"
      : budgetPct < 85
        ? "bg-warning"
        : "bg-destructive"

  return (
    <button
      onClick={() => onSelect(stage.id)}
      className={`
        w-[200px] rounded-xl border glass-edge p-3.5
        transition-all duration-200 cursor-pointer text-left
        ${STATUS_BORDER[stage.status]}
        ${STATUS_GLOW[stage.status]}
        ${selected ? "neon-glow ring-1 ring-governance/30" : "hover:border-governance/30"}
      `}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            stage.status === "healthy"
              ? "bg-governance"
              : stage.status === "warning"
                ? "bg-warning"
                : "bg-destructive"
          }`}
        />
        <span className="text-xs text-foreground font-medium truncate">
          {stage.name}
        </span>
      </div>

      {/* Metrics */}
      <div className="flex items-baseline justify-between mb-2">
        <div>
          <span className="font-mono text-[9px] text-muted-foreground/50 uppercase block">P99</span>
          <span className="font-mono text-sm text-foreground">{formatMs(stage.latency.p99_ms)}</span>
        </div>
        <div className="text-right">
          <span className="font-mono text-[9px] text-muted-foreground/50 uppercase block">Processed</span>
          <span className="font-mono text-sm text-foreground">{formatCount(stage.total_processed)}</span>
        </div>
      </div>

      {/* Budget bar */}
      <div className="h-1 rounded-full bg-card/80 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${budgetPct}%` }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="font-mono text-[8px] text-muted-foreground/40">
          {budgetPct.toFixed(0)}% budget
        </span>
        {stage.recent_violations > 0 && (
          <span className="font-mono text-[8px] text-warning">
            {stage.recent_violations} violations
          </span>
        )}
      </div>
    </button>
  )
}

const nodeTypes = { stageNode: StageNode }

function layoutNodes(
  stages: PipelineStage[],
  direction: "LR" | "TB",
): { nodes: Node<StageNodeData>[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir: direction,
    nodesep: direction === "LR" ? 60 : 40,
    ranksep: direction === "LR" ? 80 : 60,
  })

  const nodeList: Node<StageNodeData>[] = stages.map((stage) => {
    g.setNode(stage.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
    return {
      id: stage.id,
      type: "stageNode",
      position: { x: 0, y: 0 },
      data: { stage, selected: false, onSelect: () => {} },
      sourcePosition: direction === "LR" ? Position.Right : Position.Bottom,
      targetPosition: direction === "LR" ? Position.Left : Position.Top,
    }
  })

  const edgeList: Edge[] = []
  for (let i = 0; i < stages.length - 1; i++) {
    const edgeId = `${stages[i].id}->${stages[i + 1].id}`
    g.setEdge(stages[i].id, stages[i + 1].id)
    edgeList.push({
      id: edgeId,
      source: stages[i].id,
      target: stages[i + 1].id,
      type: "smoothstep",
      animated: true,
      style: { stroke: "oklch(0.88 0.20 155 / 0.4)", strokeWidth: 2 },
    })
  }

  dagre.layout(g)

  for (const node of nodeList) {
    const pos = g.node(node.id)
    node.position = {
      x: pos.x - NODE_WIDTH / 2,
      y: pos.y - NODE_HEIGHT / 2,
    }
  }

  return { nodes: nodeList, edges: edgeList }
}

interface Props {
  stages: PipelineStage[]
  selectedStageId: string | null
  onStageSelect: (id: string) => void
}

export function PipelineFlow({ stages, selectedStageId, onStageSelect }: Props) {
  const [containerWidth, setContainerWidth] = useState(800)

  useEffect(() => {
    function handleResize() {
      setContainerWidth(window.innerWidth)
    }
    handleResize()
    window.addEventListener("resize", handleResize)
    return () => window.removeEventListener("resize", handleResize)
  }, [])

  const direction = containerWidth < 768 ? "TB" : "LR"

  const { initialNodes, initialEdges } = useMemo(() => {
    const { nodes, edges } = layoutNodes(stages, direction as "LR" | "TB")
    // Inject selection state and callback
    const withCallbacks = nodes.map((n) => ({
      ...n,
      data: {
        ...n.data,
        selected: n.id === selectedStageId,
        onSelect: onStageSelect,
      },
    }))
    return { initialNodes: withCallbacks, initialEdges: edges }
  }, [stages, direction, selectedStageId, onStageSelect])

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)

  useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  const flowHeight = direction === "TB" ? 580 : 200

  return (
    <div
      className="rounded-xl border border-border/40 glass-edge overflow-hidden"
      style={{ height: flowHeight }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background
          color="oklch(0.25 0.01 250 / 0.3)"
          gap={20}
          size={1}
        />
      </ReactFlow>
    </div>
  )
}
