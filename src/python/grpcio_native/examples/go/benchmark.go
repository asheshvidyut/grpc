package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"math"
	"math/rand"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"go_server/pb"
)

func main() {
	target := flag.String("target", "localhost:50099", "Server address to benchmark")
	size := flag.Int64("size", 1024*1024*1024, "Payload size in bytes (default 1GB)")
	samples := flag.Int("samples", 5, "Number of latency samples")
	warmup := flag.Int("warmup", 1, "Number of warmup calls")
	flag.Parse()

	sizeGB := float64(*size) / (1024 * 1024 * 1024)
	fmt.Printf("Benchmarking Target: %s\n", *target)
	fmt.Printf("Payload Size: %d bytes (%.3f GB)\n", *size, sizeGB)
	fmt.Printf("Samples: %d, Warmup: %d\n\n", *samples, *warmup)

	// Generate payload of specified size
	fmt.Println("Generating payload in memory...")
	payloadBytes := make([]byte, *size)
	// Fill with a simple character to avoid blank string optimize
	for i := range payloadBytes {
		payloadBytes[i] = 'x'
	}
	payload := string(payloadBytes)
	// Free helper slice memory ASAP
	payloadBytes = nil

	// Establish connection with unlimited message sizes
	conn, err := grpc.Dial(
		*target,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithDefaultCallOptions(
			grpc.MaxCallRecvMsgSize(math.MaxInt32),
			grpc.MaxCallSendMsgSize(math.MaxInt32),
		),
	)
	if err != nil {
		log.Fatalf("Did not connect: %v", err)
	}
	defer conn.Close()

	client := pb.NewEchoServiceClient(conn)
	req := &pb.EchoRequest{Message: payload}

	// WARMUP
	if *warmup > 0 {
		fmt.Println("Running warmup calls...")
		for i := 0; i < *warmup; i++ {
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			t0 := time.Now()
			_, err := client.Echo(ctx, req)
			cancel()
			if err != nil {
				log.Fatalf("Warmup call failed: %v", err)
			}
			fmt.Printf("  Warmup %d completed in %v\n", i+1, time.Since(t0))
		}
	}

	// SAMPLING
	fmt.Println("\nRunning latency sampling...")
	var latencies []time.Duration
	var totalDuration time.Duration

	for i := 0; i < *samples; i++ {
		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		t0 := time.Now()
		resp, err := client.Echo(ctx, req)
		elapsed := time.Since(t0)
		cancel()
		if err != nil {
			log.Fatalf("Latency call %d failed: %v", i+1, err)
		}
		if len(resp.GetMessage()) != len(payload) {
			log.Fatalf("Response verification failed! Sent %d, got %d bytes", len(payload), len(resp.GetMessage()))
		}
		latencies = append(latencies, elapsed)
		totalDuration += elapsed
		fmt.Printf("  Sample %d: %v (Throughput: %.2f GB/s)\n", i+1, elapsed, sizeGB/elapsed.Seconds())
		
		// Let GC run or give the system a tiny breath between 1GB calls
		time.Sleep(200 * time.Millisecond)
	}

	// Compute stats
	var minDur, maxDur, sumDur time.Duration
	minDur = latencies[0]
	maxDur = latencies[0]
	for _, d := range latencies {
		if d < minDur {
			minDur = d
		}
		if d > maxDur {
			maxDur = d
		}
		sumDur += d
	}
	meanDur := sumDur / time.Duration(len(latencies))

	fmt.Println("\n=================== RESULTS ===================")
	fmt.Printf("Target:                   %s\n", *target)
	fmt.Printf("Min Latency:              %v\n", minDur)
	fmt.Printf("Max Latency:              %v\n", maxDur)
	fmt.Printf("Mean Latency:             %v\n", meanDur)
	fmt.Printf("Effective Latency QPS:    %.2f req/sec\n", 1.0/meanDur.Seconds())
	fmt.Printf("Average Read/Write Speed: %.2f GB/s\n", sizeGB/meanDur.Seconds())
	fmt.Println("===============================================")
}

// Helper for random string if needed
func init() {
	rand.Seed(time.Now().UnixNano())
}
