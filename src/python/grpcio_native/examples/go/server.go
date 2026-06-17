package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"math"
	"net"
	"strings"

	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
	"go_server/pb"
)

type server struct {
	pb.UnimplementedEchoServiceServer
}

func (s *server) Echo(ctx context.Context, req *pb.EchoRequest) (*pb.EchoResponse, error) {
	return &pb.EchoResponse{Message: req.GetMessage()}, nil
}

func (s *server) EchoStream(req *pb.EchoRequest, stream pb.EchoService_EchoStreamServer) error {
	msg := req.GetMessage()
	words := strings.Split(msg, " ")
	for _, word := range words {
		if word == "" {
			continue
		}
		err := stream.Send(&pb.EchoResponse{Message: word})
		if err != nil {
			return err
		}
	}
	return nil
}

func main() {
	port := flag.Int("port", 50099, "Port to listen on")
	flag.Parse()

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", *port))
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	// Setup gRPC server options to support large messages (up to 2GB)
	opts := []grpc.ServerOption{
		grpc.MaxRecvMsgSize(math.MaxInt32),
		grpc.MaxSendMsgSize(math.MaxInt32),
	}

	s := grpc.NewServer(opts...)
	pb.RegisterEchoServiceServer(s, &server{})
	reflection.Register(s)

	log.Printf("Go gRPC Server listening on port %d with unlimited max message sizes", *port)
	if err := s.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}
