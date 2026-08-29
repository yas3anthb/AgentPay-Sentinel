"use client";

import { Line, OrbitControls, RoundedBox, Text } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import {
  STAGES,
  STAGE_INDEX,
  severedAt,
  statusColor,
  type PipelineState,
  type StageStatus,
} from "@/lib/pipeline";

const SPACING = 2.1;
const IDLE = "#CBD5E1";
const SURFACE = "#FFFFFF";
const GROUND = "#EEF0F3";

/**
 * A solid rounded node per stage on a light ground, restyled from the earlier
 * neon-wireframe treatment to match the product's enterprise palette. Every
 * node shares the same rounded-box silhouette — consistent with the step
 * tracker above it — so the two views read as one system rather than two
 * competing visual languages; only the status colour and a small label change.
 */
function StageNode({
  index,
  status,
  reducedMotion,
}: {
  index: number;
  status: StageStatus;
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const color = status === "idle" ? IDLE : statusColor(status);
  const active = status !== "idle" && status !== "skipped";

  useFrame((_, delta) => {
    if (reducedMotion || !group.current) return;
    if (status === "started") group.current.rotation.y += delta * 0.6;
  });

  return (
    <group position={[index * SPACING, 0, 0]}>
      <group ref={group}>
        <RoundedBox args={[0.78, 0.78, 0.78]} radius={0.1} smoothness={4}>
          <meshStandardMaterial
            color={active ? color : SURFACE}
            roughness={0.55}
            metalness={0.02}
          />
        </RoundedBox>
        <RoundedBox args={[0.8, 0.8, 0.8]} radius={0.11} smoothness={4}>
          <meshBasicMaterial color={color} wireframe transparent opacity={0.35} />
        </RoundedBox>
      </group>

      {status === "started" && !reducedMotion ? (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.62, 0]}>
          <ringGeometry args={[0.52, 0.58, 32]} />
          <meshBasicMaterial color={color} transparent opacity={0.4} side={THREE.DoubleSide} />
        </mesh>
      ) : null}

      <Text
        position={[0, -0.82, 0]}
        fontSize={0.15}
        color={active ? "#1A2233" : "#8A93A3"}
        anchorX="center"
        anchorY="top"
        font={undefined}
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

      if (breakAt !== null && i >= breakAt) {
        out.push({ from: i, to: i + 1, color: "#D2D7E0", dashed: true });
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
            [segment.from * SPACING + 0.5, 0, 0],
            [segment.to * SPACING - 0.5, 0, 0],
          ]}
          color={segment.color}
          lineWidth={segment.dashed ? 1.5 : 2.5}
          dashed={segment.dashed}
          dashSize={0.08}
          gapSize={0.08}
          transparent
          opacity={segment.dashed ? 0.5 : 0.9}
        />
      ))}
      {breakAt !== null ? (
        <BreakMark x={breakAt * SPACING + 0.72} reducedMotion={reducedMotion} />
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
    group.current.scale.setScalar(1 + Math.sin(t * 5) * 0.06);
  });
  return (
    <group ref={group} position={[x, 0, 0]}>
      <mesh>
        <circleGeometry args={[0.13, 24]} />
        <meshBasicMaterial color="#C2334A" />
      </mesh>
      <Line
        points={[
          [-0.06, 0.06, 0.01],
          [0.06, -0.06, 0.01],
        ]}
        color="#FFFFFF"
        lineWidth={2}
      />
      <Line
        points={[
          [0.06, 0.06, 0.01],
          [-0.06, -0.06, 0.01],
        ]}
        color="#FFFFFF"
        lineWidth={2}
      />
    </group>
  );
}

function Rig({ reducedMotion, idle }: { reducedMotion: boolean; idle: boolean }) {
  const centre = ((STAGES.length - 1) * SPACING) / 2;
  useFrame((state) => {
    if (reducedMotion || !idle) return;
    const t = state.clock.elapsedTime * 0.1;
    state.camera.position.x = centre + Math.sin(t) * 0.6;
    state.camera.position.z = 8.5 + Math.cos(t) * 0.4;
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
      camera={{ position: [centre, 2.6, 8.5], fov: 36 }}
      gl={{ antialias: true, alpha: false }}
      dpr={[1, 2]}
    >
      <color attach="background" args={[GROUND]} />
      <ambientLight intensity={0.85} />
      <directionalLight position={[4, 6, 5]} intensity={0.6} />
      <directionalLight position={[-4, 3, -3]} intensity={0.2} />

      <group position={[-centre, 0, 0]} rotation={[0.12, -0.18, 0]}>
        {STAGES.map((stage) => (
          <StageNode
            key={stage.id}
            index={STAGE_INDEX[stage.id]}
            status={state[stage.id].status}
            reducedMotion={reducedMotion}
          />
        ))}
        <Beam state={state} reducedMotion={reducedMotion} />
        <gridHelper args={[24, 24, "#D2D7E0", "#E3E6EB"]} position={[centre, -1.3, 0]} />
      </group>
      <Rig reducedMotion={reducedMotion} idle={idle} />
      <OrbitControls
        enablePan={false}
        enableZoom
        minDistance={5}
        maxDistance={14}
        target={[0, 0, 0]}
        enabled={!idle}
      />
    </Canvas>
  );
}
