"use client";

import { Line, OrbitControls, Text } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import {
  STAGES,
  STAGE_INDEX,
  severedAt,
  statusColor,
  type PipelineState,
  type StageId,
  type StageStatus,
} from "@/lib/pipeline";

const SPACING = 2.15;
const IDLE = "#243343";

/**
 * A distinct abstract form per stage, so the scene reads as a machine rather
 * than seven identical boxes. No default lighting rig and no default material:
 * everything is emissive wireframe against a near-black ground, which is the
 * same visual language as the rest of the app.
 */
function StageGeometry({ id }: { id: StageId }) {
  switch (id) {
    case "identity":
      return <torusGeometry args={[0.42, 0.06, 8, 24]} />;
    case "canonical":
      return <boxGeometry args={[0.62, 0.62, 0.62]} />;
    case "analyzer":
      // The LLM classifier: many-faceted, and the only one that spins.
      return <icosahedronGeometry args={[0.5, 0]} />;
    case "risk":
      return <octahedronGeometry args={[0.55, 0]} />;
    case "pdp":
      // The policy engine: a lattice of rules.
      return <boxGeometry args={[0.72, 0.72, 0.72, 2, 2, 2]} />;
    case "authorization":
      return <cylinderGeometry args={[0.34, 0.34, 0.7, 6]} />;
    case "audit":
      return <torusKnotGeometry args={[0.32, 0.1, 64, 8, 2, 3]} />;
  }
}

function StageNode({
  id,
  index,
  status,
  reducedMotion,
}: {
  id: StageId;
  index: number;
  status: StageStatus;
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const ring = useRef<THREE.Mesh>(null);
  const color = status === "idle" ? IDLE : statusColor(status);
  const active = status !== "idle" && status !== "skipped";

  useFrame((state, delta) => {
    if (reducedMotion || !group.current) return;
    // Only the classifier idles with a spin; the rest stay still so movement
    // means something.
    if (id === "analyzer") group.current.rotation.y += delta * 0.35;
    if (status === "started") group.current.rotation.y += delta * 0.9;

    if (ring.current) {
      const t = state.clock.elapsedTime;
      const scale = status === "started" ? 1 + Math.sin(t * 4) * 0.12 : 1;
      ring.current.scale.setScalar(scale);
    }
  });

  return (
    <group position={[index * SPACING, 0, 0]}>
      <group ref={group}>
        <mesh>
          <StageGeometry id={id} />
          <meshBasicMaterial color={color} wireframe transparent opacity={active ? 0.95 : 0.4} />
        </mesh>
      </group>

      {/* Halo: presence without a light rig. */}
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.62, 0]}>
        <ringGeometry args={[0.5, 0.56, 32]} />
        <meshBasicMaterial
          color={color}
          transparent
          opacity={active ? 0.5 : 0.12}
          side={THREE.DoubleSide}
        />
      </mesh>

      <Text
        position={[0, -0.95, 0]}
        fontSize={0.16}
        color={active ? color : "#4F6072"}
        anchorX="center"
        anchorY="top"
      >
        {STAGES[index].short}
      </Text>
    </group>
  );
}

function Beam({ state, reducedMotion }: { state: PipelineState; reducedMotion: boolean }) {
  const breakAt = severedAt(state);
  const last = STAGES.length - 1;

  const segments = useMemo(() => {
    const out: { from: number; to: number; color: string; dashed: boolean }[] = [];
    for (let i = 0; i < last; i += 1) {
      const fromStage = STAGES[i].id;
      const toStage = STAGES[i + 1].id;
      const fromStatus = state[fromStage].status;
      const toStatus = state[toStage].status;

      // The beam physically stops at the blocking node.
      if (breakAt !== null && i >= breakAt) {
        out.push({ from: i, to: i + 1, color: "#2A3644", dashed: true });
        continue;
      }
      const carried = fromStatus !== "idle" && toStatus !== "idle";
      out.push({
        from: i,
        to: i + 1,
        color: carried ? statusColor(toStatus) : IDLE,
        dashed: !carried,
      });
    }
    return out;
  }, [state, breakAt, last]);

  return (
    <>
      {segments.map((segment) => (
        <Line
          key={segment.from}
          points={[
            [segment.from * SPACING + 0.55, 0, 0],
            [segment.to * SPACING - 0.55, 0, 0],
          ]}
          color={segment.color}
          lineWidth={segment.dashed ? 1 : 2}
          dashed={segment.dashed}
          dashSize={0.08}
          gapSize={0.08}
          transparent
          opacity={segment.dashed ? 0.35 : 0.95}
        />
      ))}

      {breakAt !== null ? (
        <BreakMark x={breakAt * SPACING + 0.75} reducedMotion={reducedMotion} />
      ) : null}
    </>
  );
}

/** The visible severance: a rupture drawn exactly where the decision stopped. */
function BreakMark({ x, reducedMotion }: { x: number; reducedMotion: boolean }) {
  const group = useRef<THREE.Group>(null);
  useFrame((state) => {
    if (reducedMotion || !group.current) return;
    const t = state.clock.elapsedTime;
    group.current.scale.setScalar(1 + Math.sin(t * 6) * 0.08);
  });
  return (
    <group ref={group} position={[x, 0, 0]}>
      <Line
        points={[
          [-0.14, 0.3, 0],
          [0.14, -0.3, 0],
        ]}
        color="#F2637A"
        lineWidth={2.5}
      />
      <Line
        points={[
          [0.14, 0.3, 0],
          [-0.14, -0.3, 0],
        ]}
        color="#F2637A"
        lineWidth={2.5}
      />
    </group>
  );
}

function Rig({ reducedMotion, idle }: { reducedMotion: boolean; idle: boolean }) {
  const centre = ((STAGES.length - 1) * SPACING) / 2;
  useFrame((state) => {
    if (reducedMotion || !idle) return;
    // A slow drift while nothing is in flight; dead still during a run so the
    // motion you see is the pipeline, not the camera.
    const t = state.clock.elapsedTime * 0.12;
    state.camera.position.x = centre + Math.sin(t) * 0.7;
    state.camera.position.z = 9.5 + Math.cos(t) * 0.5;
    state.camera.lookAt(centre, 0, 0);
  });
  return null;
}

export function Scene3D({
  state,
  reducedMotion,
  idle,
}: {
  state: PipelineState;
  reducedMotion: boolean;
  idle: boolean;
}) {
  const centre = ((STAGES.length - 1) * SPACING) / 2;

  return (
    <Canvas
      camera={{ position: [centre, 3.2, 9.5], fov: 38 }}
      gl={{ antialias: true, alpha: true }}
      dpr={[1, 2]}
    >
      <group position={[-centre, 0, 0]} rotation={[0.18, -0.22, 0]}>
        {STAGES.map((stage) => (
          <StageNode
            key={stage.id}
            id={stage.id}
            index={STAGE_INDEX[stage.id]}
            status={state[stage.id].status}
            reducedMotion={reducedMotion}
          />
        ))}
        <Beam state={state} reducedMotion={reducedMotion} />
        <gridHelper
          args={[26, 26, "#111A24", "#0C141C"]}
          position={[centre, -1.4, 0]}
        />
      </group>
      <Rig reducedMotion={reducedMotion} idle={idle} />
      <OrbitControls
        enablePan={false}
        enableZoom
        minDistance={5}
        maxDistance={16}
        target={[0, 0, 0]}
        enabled={!idle}
      />
    </Canvas>
  );
}
